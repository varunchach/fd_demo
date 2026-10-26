"""Fraud MLOps — simple KFP pipeline for OpenShift AI (demo).

  1. ingest_from_s3       — load CSV from S3 (auto-seeds if missing)
  2. process_features     — Feast online features (falls back to ingest)
  3. train_log_register   — train, log MLflow, save model pickle to S3

Serving is GitOps (OVMS InferenceService), not built inside the pipeline.
Compile:  python pipeline/pipeline.py
"""
from kfp import compiler, dsl

# Must match feature_repo/features.py + docs/FEATURE_DICTIONARY.md
FEATURES = [
    "geo_distance_from_last_txn",
    "spend_vs_median_ratio",
    "card_chip_present",
    "pin_authenticated",
    "ecommerce_channel",
    "known_merchant_repeat",
]
FEATURE_VIEW = "fraud_txn_risk_signals"


@dsl.component(base_image="python:3.11", packages_to_install=["boto3==1.35.36", "pandas==2.2.3", "numpy==1.26.4"])
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

    names = [
        "geo_distance_from_last_txn",
        "spend_vs_median_ratio",
        "card_chip_present",
        "pin_authenticated",
        "ecommerce_channel",
        "known_merchant_repeat",
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
        # Interpretable synthetic txn risk signals (km, spend ratio, 0/1 flags)
        import numpy as np

        rng = np.random.default_rng(42)
        n = 100
        fraud = rng.random(n) < 0.1
        geo = np.where(fraud, rng.uniform(200, 4000, n), rng.exponential(12.0, n).clip(0, 80))
        spend = np.where(
            fraud,
            rng.uniform(4.0, 18.0, n),
            rng.lognormal(0.0, 0.35, n).clip(0.2, 3.5),
        )
        ecommerce = np.where(fraud, 1, (rng.random(n) < 0.35).astype(int))
        chip = np.where(ecommerce == 1, 0, (rng.random(n) < 0.85).astype(int))
        pin = np.where((chip == 1) & (ecommerce == 0), (rng.random(n) < 0.9).astype(int), 0)
        known = np.where(fraud, 0, (rng.random(n) < 0.7).astype(int))
        df = pd.DataFrame(
            {
                "geo_distance_from_last_txn": geo,
                "spend_vs_median_ratio": spend,
                "card_chip_present": chip,
                "pin_authenticated": pin,
                "ecommerce_channel": ecommerce,
                "known_merchant_repeat": known,
                "fraud": fraud.astype(int),
                "transaction_id": range(n),
            }
        )
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
        "geo_distance_from_last_txn",
        "spend_vs_median_ratio",
        "card_chip_present",
        "pin_authenticated",
        "ecommerce_channel",
        "known_merchant_repeat",
    ]
    feature_view = "fraud_txn_risk_signals"
    raw = pd.read_csv(input_data.path)
    if "transaction_id" not in raw.columns:
        raw["transaction_id"] = raw.index
    ids = raw["transaction_id"].astype(int).tolist()
    labels = raw["fraud"].tolist() if "fraud" in raw.columns else [0] * len(ids)

    rows = []
    feast_ok = False
    try:
        for start in range(0, len(ids), 500):
            batch = ids[start : start + 500]
            r = requests.post(
                f"{feast_online_server_url.rstrip('/')}/get-online-features",
                json={
                    "features": [f"{feature_view}:{n}" for n in names],
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
        feast_ok = True
    except Exception as exc:
        print(f"Feast online unavailable ({exc}); falling back to ingest columns")

    if feast_ok and rows:
        out = pd.concat(rows, ignore_index=True)
        keep = [c for c in out.columns if c in names or c == "transaction_id"]
        out = out[keep].copy()
    else:
        out = raw.copy()
        if "transaction_id" not in out.columns:
            out["transaction_id"] = out.index

    # Fill any missing feature columns from ingest
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
    print(f"Feature step rows={len(out)} feast_ok={feast_ok}")


@dsl.component(
    base_image="python:3.11",
    packages_to_install=[
        "pandas==2.2.3",
        "scikit-learn==1.5.2",
        "mlflow[kubernetes]==3.14.0",
        "boto3==1.35.36",
    ],
)
def train_log_register(
    input_data: dsl.Input[dsl.Dataset],
    model_out: dsl.Output[dsl.Model],
    mlflow_tracking_uri: str,
    mlflow_experiment: str,
    s3_endpoint: str = "",
    s3_bucket: str = "",
    aws_access_key_id: str = "",
    aws_secret_access_key: str = "",
    model_s3_key: str = "fd-gitops/models/fraud-model.pkl",
    model_name: str = "fd-gitops-model",
):
    """Step 3: Train, log to MLflow, save model pickle to S3 (demo artifact)."""
    import io
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
        "geo_distance_from_last_txn",
        "spend_vs_median_ratio",
        "card_chip_present",
        "pin_authenticated",
        "ecommerce_channel",
        "known_merchant_repeat",
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

    artifact = {"model": model, "scaler": scaler, "features": names, "model_name": model_name}
    with open(model_out.path, "wb") as f:
        pickle.dump(artifact, f)
    model_out.metadata.update({"mlflow_run_id": run_id, **metrics})
    print(f"MLflow run={run_id} metrics={metrics} artifact={artifact_uri}")

    # Save model file to S3 (simple demo publish — serving stays GitOps/OVMS)
    if s3_endpoint and s3_bucket and aws_access_key_id:
        import boto3

        buf = io.BytesIO()
        pickle.dump(artifact, buf)
        boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name="us-east-1",
        ).put_object(Bucket=s3_bucket, Key=model_s3_key, Body=buf.getvalue())
        print(f"Saved s3://{s3_bucket}/{model_s3_key}")


@dsl.pipeline(name="fd-gitops-pipeline", description="Ingest -> Features -> Train/MLflow/S3 (serve via GitOps OVMS)")
def fd_gitops_pipeline(
    s3_endpoint: str,
    s3_bucket: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    feast_online_server_url: str,
    mlflow_tracking_uri: str,
    s3_key: str = "fd-gitops/raw/transactions.csv",
    mlflow_experiment: str = "fd-gitops-training",
    model_s3_key: str = "fd-gitops/models/fraud-model.pkl",
    model_name: str = "fd-gitops-model",
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
        s3_endpoint=s3_endpoint,
        s3_bucket=s3_bucket,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        model_s3_key=model_s3_key,
        model_name=model_name,
    )


if __name__ == "__main__":
    out = __file__.replace(".py", ".yaml")
    compiler.Compiler().compile(fd_gitops_pipeline, out)
    print(f"Compiled {out}")
