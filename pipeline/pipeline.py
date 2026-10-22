"""Fraud MLOps — 3-step KFP pipeline for OpenShift AI 3.5.

  1. ingest_from_s3       — load CSV from S3 (auto-seeds if missing)
  2. process_features     — pull online features from Feast Feature Store
  3. train_log_register   — train, log to MLflow, optional Model Registry

Compile:  python pipeline/pipeline.py
"""
from kfp import compiler, dsl

FEATURES = [
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "used_chip",
    "used_pin_number",
    "online_order",
    "repeat_retailer",
]


@dsl.component(base_image="python:3.11", packages_to_install=["boto3==1.35.36", "pandas==2.2.3", "scikit-learn==1.5.2"])
def ingest_from_s3(
    output_data: dsl.Output[dsl.Dataset],
    s3_endpoint: str,
    s3_bucket: str,
    s3_key: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
):
    """Step 1: Ingest raw transactions from S3. Creates object on first run."""
    import io

    import boto3
    import pandas as pd
    from botocore.exceptions import ClientError
    from sklearn.datasets import make_classification

    names = [
        "distance_from_last_transaction",
        "ratio_to_median_purchase_price",
        "used_chip",
        "used_pin_number",
        "online_order",
        "repeat_retailer",
    ]
    client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name="us-east-1",
    )
    try:
        client.head_bucket(Bucket=s3_bucket)
    except ClientError:
        client.create_bucket(Bucket=s3_bucket)

    try:
        body = client.get_object(Bucket=s3_bucket, Key=s3_key)["Body"].read()
        df = pd.read_csv(io.BytesIO(body))
        print(f"Loaded s3://{s3_bucket}/{s3_key} ({len(df)} rows)")
    except ClientError:
        X, y = make_classification(
            n_samples=100, n_features=len(names), n_informative=4,
            n_redundant=0, weights=[0.9, 0.1], class_sep=1.2, random_state=42,
        )
        df = pd.DataFrame(X, columns=names)
        df["fraud"] = y
        df["transaction_id"] = df.index
        buf = io.BytesIO()
        df.to_csv(buf, index=False)
        client.put_object(Bucket=s3_bucket, Key=s3_key, Body=buf.getvalue())
        print(f"Seeded + loaded s3://{s3_bucket}/{s3_key} ({len(df)} rows)")

    df.to_csv(output_data.path, index=False)


@dsl.component(base_image="python:3.11", packages_to_install=["pandas==2.2.3", "requests==2.32.3"])
def process_features(
    input_data: dsl.Input[dsl.Dataset],
    output_data: dsl.Output[dsl.Dataset],
    feast_online_server_url: str,
):
    """Step 2: Join Feast online features with labels from S3 ingest."""
    import pandas as pd
    import requests

    names = [
        "distance_from_last_transaction",
        "ratio_to_median_purchase_price",
        "used_chip",
        "used_pin_number",
        "online_order",
        "repeat_retailer",
    ]
    raw = pd.read_csv(input_data.path)
    if "transaction_id" not in raw.columns:
        raw["transaction_id"] = raw.index
    ids = raw["transaction_id"].astype(int).tolist()
    labels = raw["fraud"].tolist() if "fraud" in raw.columns else [0] * len(ids)

    rows = []
    for start in range(0, len(ids), 500):
        batch = ids[start : start + 500]
        r = requests.post(
            f"{feast_online_server_url.rstrip('/')}/get-online-features",
            json={
                "features": [f"fraud_features:{n}" for n in names],
                "entities": {"transaction_id": batch},
            },
            timeout=60,
            verify=False,
        )
        r.raise_for_status()
        body = r.json()
        rows.append(
            pd.DataFrame(
                dict(zip(body["metadata"]["feature_names"], [x["values"] for x in body["results"]]))
            )
        )

    out = pd.concat(rows, ignore_index=True)
    keep = [c for c in out.columns if c in names or c == "transaction_id"]
    out = out[keep].copy()
    # Online store may be empty (no materialize) — fall back to ingest columns
    raw_by_id = raw.set_index("transaction_id", drop=False)
    for n in names:
        if n not in out.columns:
            out[n] = float("nan")
        miss = out[n].isna() if n in out.columns else pd.Series([True] * len(out))
        if miss.any() and n in raw.columns:
            out.loc[miss, n] = (
                out.loc[miss, "transaction_id"].map(raw_by_id[n]).to_numpy()
                if "transaction_id" in out.columns
                else raw[n].iloc[: miss.sum()].to_numpy()
            )
    out[names] = out[names].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    out["fraud"] = labels[: len(out)]
    out.to_csv(output_data.path, index=False)
    print(f"Feature Store returned {len(out)} rows (fillna/fallback applied)")


@dsl.component(
    base_image="python:3.11",
    packages_to_install=[
        "pandas==2.2.3",
        "scikit-learn==1.5.2",
        "mlflow[kubernetes]==3.14.0",
        "model-registry==0.2.21",
    ],
)
def train_log_register(
    input_data: dsl.Input[dsl.Dataset],
    model_out: dsl.Output[dsl.Model],
    mlflow_tracking_uri: str,
    mlflow_experiment: str,
    registry_server_address: str = "",
    model_name: str = "fd-gitops-model",
    model_version: str = "1.0.0",
):
    """Step 3: Train sklearn model, log to MLflow, optionally register."""
    import json
    import os
    import pickle

    import mlflow
    import mlflow.sklearn
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    names = [
        "distance_from_last_transaction",
        "ratio_to_median_purchase_price",
        "used_chip",
        "used_pin_number",
        "online_order",
        "repeat_retailer",
    ]

    df = pd.read_csv(input_data.path)
    X = df[names].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = df["fraud"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    scaler = StandardScaler().fit(X_tr)
    X_tr_s, X_te_s = scaler.transform(X_tr), scaler.transform(X_te)

    # RHOAI MLflow (workspaces): X-MLFLOW-WORKSPACE + SA token.
    # KFP injects KFP_MLFLOW_CONFIG when DSPA mlflow.integrationMode=AUTODETECT.
    parent = None
    kfp_mlflow = os.environ.get("KFP_MLFLOW_CONFIG")
    if kfp_mlflow:
        cfg = json.loads(kfp_mlflow)
        uri = cfg.get("endpoint") or mlflow_tracking_uri
        workspace = cfg.get("workspace") or os.environ.get("MLFLOW_WORKSPACE", "fd-gitops")
        os.environ["MLFLOW_TRACKING_URI"] = uri
        os.environ["MLFLOW_WORKSPACE"] = workspace
        os.environ["MLFLOW_TRACKING_AUTH"] = "kubernetes-namespaced"
        os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        if os.path.exists(token_path):
            with open(token_path, encoding="utf-8") as tf:
                os.environ["MLFLOW_TRACKING_TOKEN"] = tf.read().strip()
        mlflow.set_tracking_uri(uri)
        exp_id = cfg.get("experimentId")
        if exp_id:
            mlflow.set_experiment(experiment_id=str(exp_id))
        else:
            mlflow.set_experiment(mlflow_experiment)
        parent = cfg.get("parentRunId")
    else:
        uri = mlflow_tracking_uri
        if uri.startswith("file:"):
            uri = "sqlite:////tmp/mlflow-fraud.db"
        # Allow callers to pass a cluster URI with workspace via env
        if uri.startswith("http") and "MLFLOW_WORKSPACE" not in os.environ:
            os.environ["MLFLOW_WORKSPACE"] = os.environ.get("NAMESPACE", "fd-gitops")
            os.environ["MLFLOW_TRACKING_AUTH"] = "kubernetes-namespaced"
            os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(mlflow_experiment)

    run_ctx = (
        mlflow.start_run(run_name="fd-gitops", parent_run_id=parent)
        if parent
        else mlflow.start_run(run_name="fd-gitops")
    )

    with run_ctx as run:
        model = LogisticRegression(max_iter=200, class_weight="balanced")
        model.fit(X_tr_s, y_tr)
        pred = model.predict(X_te_s)
        metrics = {
            "accuracy": float(accuracy_score(y_te, pred)),
            "precision": float(precision_score(y_te, pred, zero_division=0)),
            "recall": float(recall_score(y_te, pred, zero_division=0)),
        }
        mlflow.log_params({"model_type": "logistic_regression", "class_weight": "balanced"})
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(model, "model")
        run_id = run.info.run_id
        artifact_uri = mlflow.get_artifact_uri("model")

    with open(model_out.path, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler}, f)
    model_out.metadata.update({"mlflow_run_id": run_id, **metrics})
    print(f"MLflow run={run_id} metrics={metrics}")

    if registry_server_address:
        from model_registry import ModelRegistry

        reg = ModelRegistry(server_address=registry_server_address, port=443, author="fd-gitops")
        v = reg.register_model(
            name=model_name,
            uri=artifact_uri,
            version=model_version,
            model_format_name="sklearn",
            model_format_version="1",
            metadata={"mlflow_run_id": run_id, **metrics},
        )
        print(f"Registered {model_name} id={getattr(v, 'id', model_version)}")


@dsl.pipeline(name="fd-gitops-pipeline", description="S3 -> Feature Store -> Train/MLflow (fd-gitops)")
def fd_gitops_pipeline(
    s3_endpoint: str,
    s3_bucket: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    feast_online_server_url: str,
    mlflow_tracking_uri: str,
    s3_key: str = "fd-gitops/raw/transactions.csv",
    mlflow_experiment: str = "fd-gitops-training",
    registry_server_address: str = "",
    model_name: str = "fd-gitops-model",
    model_version: str = "1.0.0",
):
    raw = ingest_from_s3(
        s3_endpoint=s3_endpoint,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    feats = process_features(
        input_data=raw.outputs["output_data"],
        feast_online_server_url=feast_online_server_url,
    )
    train_log_register(
        input_data=feats.outputs["output_data"],
        mlflow_tracking_uri=mlflow_tracking_uri,
        mlflow_experiment=mlflow_experiment,
        registry_server_address=registry_server_address,
        model_name=model_name,
        model_version=model_version,
    )


if __name__ == "__main__":
    out = __file__.replace(".py", ".yaml")
    compiler.Compiler().compile(fd_gitops_pipeline, out)
    print(f"Compiled {out}")
