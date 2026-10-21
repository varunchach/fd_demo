"""Fraud MLOps KFP v2 pipeline — 3 demo steps for RHOAI 3.5.

  1. ingest_from_s3          — pull raw transactions from object storage
  2. process_features        — engineer features + retrieve from Feast online store
  3. train_log_register      — train sklearn model, log to MLflow, register in Model Registry

Compile:  python pipeline/pipeline.py
"""
from kfp import compiler, dsl

FEATURE_NAMES = [
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "used_chip",
    "used_pin_number",
    "online_order",
    "repeat_retailer",
]


@dsl.component(packages_to_install=["boto3==1.35.36", "pandas==2.2.3"])
def ingest_from_s3(
    output_data: dsl.Output[dsl.Dataset],
    s3_endpoint: str,
    s3_bucket: str,
    s3_key: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
):
    """Step 1: Download raw training CSV from S3-compatible storage (MinIO)."""
    import io

    import boto3
    import pandas as pd

    client = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name="us-east-1",
    )
    obj = client.get_object(Bucket=s3_bucket, Key=s3_key)
    df = pd.read_csv(io.BytesIO(obj["Body"].read()))
    df.to_csv(output_data.path, index=False)
    print(f"Ingested {len(df)} rows from s3://{s3_bucket}/{s3_key}")


@dsl.component(packages_to_install=["pandas==2.2.3", "requests==2.32.3"])
def process_features(
    input_data: dsl.Input[dsl.Dataset],
    output_data: dsl.Output[dsl.Dataset],
    feast_online_server_url: str,
):
    """Step 2: Feature processing — pull online features from the Feature Store.

    The FeatureStore CR already ran `feast apply` + materialize from feature_repo/.
    This step joins Feast online features with labels from the ingested CSV
    (labels stay outside the feature store — standard Feast pattern).
    """
    import pandas as pd
    import requests

    feature_names = [
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
    entity_ids = raw["transaction_id"].astype(int).tolist()
    labels = raw["fraud"].tolist() if "fraud" in raw.columns else [0] * len(entity_ids)

    batch_size = 500
    rows = []
    for start in range(0, len(entity_ids), batch_size):
        batch_ids = entity_ids[start : start + batch_size]
        response = requests.post(
            f"{feast_online_server_url.rstrip('/')}/get-online-features",
            json={
                "features": [f"fraud_features:{name}" for name in feature_names],
                "entities": {"transaction_id": batch_ids},
            },
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        batch_df = pd.DataFrame(
            dict(zip(body["metadata"]["feature_names"], [r["values"] for r in body["results"]]))
        )
        rows.append(batch_df)

    features = pd.concat(rows, ignore_index=True)
    # Keep entity id + model features; attach labels from the S3 ingest.
    keep = [c for c in features.columns if c in feature_names or c == "transaction_id"]
    out = features[keep].copy()
    out["fraud"] = labels[: len(out)]
    out.to_csv(output_data.path, index=False)
    print(f"Processed {len(out)} rows via Feature Store at {feast_online_server_url}")


@dsl.component(
    packages_to_install=[
        "pandas==2.2.3",
        "scikit-learn==1.5.2",
        "mlflow==3.14.0",
        "model-registry==0.2.21",
    ]
)
def train_log_register(
    input_data: dsl.Input[dsl.Dataset],
    model_out: dsl.Output[dsl.Model],
    mlflow_tracking_uri: str,
    mlflow_experiment: str,
    registry_server_address: str,
    model_name: str,
    model_version: str,
    register_model: bool = True,
):
    """Step 3: Train, log metrics/artifacts to MLflow, register in Model Registry."""
    import pickle

    import mlflow
    import mlflow.sklearn
    import pandas as pd
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    feature_names = [
        "distance_from_last_transaction",
        "ratio_to_median_purchase_price",
        "used_chip",
        "used_pin_number",
        "online_order",
        "repeat_retailer",
    ]
    df = pd.read_csv(input_data.path)
    X, y = df[feature_names], df["fraud"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler().fit(X_train)
    X_train_s, X_test_s = scaler.transform(X_train), scaler.transform(X_test)

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment)

    with mlflow.start_run(run_name="fraud-mlops-pipeline") as run:
        model = LogisticRegression(max_iter=200, class_weight="balanced")
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        accuracy = float(accuracy_score(y_test, preds))
        precision = float(precision_score(y_test, preds, zero_division=0))
        recall = float(recall_score(y_test, preds, zero_division=0))

        mlflow.log_param("model_type", "logistic_regression")
        mlflow.log_param("class_weight", "balanced")
        mlflow.log_metric("accuracy", accuracy)
        mlflow.log_metric("precision", precision)
        mlflow.log_metric("recall", recall)
        mlflow.sklearn.log_model(model, "model")
        run_id = run.info.run_id
        artifact_uri = mlflow.get_artifact_uri("model")

    with open(model_out.path, "wb") as f:
        pickle.dump({"model": model, "scaler": scaler}, f)

    model_out.metadata["mlflow_run_id"] = run_id
    model_out.metadata["mlflow_artifact_uri"] = artifact_uri
    model_out.metadata["accuracy"] = accuracy
    print(f"Trained: accuracy={accuracy:.4f} precision={precision:.4f} recall={recall:.4f}")
    print(f"MLflow run_id={run_id}")

    if register_model and registry_server_address:
        from model_registry import ModelRegistry

        registry = ModelRegistry(
            server_address=registry_server_address,
            port=443,
            author="fraud-mlops-pipeline",
        )
        version = registry.register_model(
            name=model_name,
            uri=artifact_uri,
            version=model_version,
            model_format_name="sklearn",
            model_format_version="1",
            metadata={
                "mlflow_run_id": run_id,
                "accuracy": accuracy,
                "precision": precision,
                "recall": recall,
            },
        )
        print(f"Registered {model_name} version={getattr(version, 'id', model_version)}")
    else:
        print("Skipping Model Registry registration (register_model=false or empty address)")


@dsl.pipeline(
    name="fraud-mlops-pipeline",
    description="S3 ingest -> Feature Store processing -> Train + MLflow + Model Registry",
)
def fraud_mlops_pipeline(
    s3_endpoint: str = "http://minio.fraud-mlops.svc.cluster.local:9000",
    s3_bucket: str = "pipeline-artifacts",
    s3_key: str = "fraud-mlops/raw/transactions.csv",
    # Pass at run time from your Data Connection / Secret (do not commit real keys).
    aws_access_key_id: str = "",
    aws_secret_access_key: str = "",
    feast_online_server_url: str = (
        "http://feast-fraud-feature-store-online.fraud-mlops.svc.cluster.local:80"
    ),
    mlflow_tracking_uri: str = "https://mlflow.redhat-ods-applications.svc:8443/mlflow",
    mlflow_experiment: str = "fraud-mlops",
    registry_server_address: str = "",
    model_name: str = "fraud-detection",
    model_version: str = "1.0.0",
    register_model: bool = False,
):
    ingest = ingest_from_s3(
        s3_endpoint=s3_endpoint,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    features = process_features(
        input_data=ingest.outputs["output_data"],
        feast_online_server_url=feast_online_server_url,
    )
    train_log_register(
        input_data=features.outputs["output_data"],
        mlflow_tracking_uri=mlflow_tracking_uri,
        mlflow_experiment=mlflow_experiment,
        registry_server_address=registry_server_address,
        model_name=model_name,
        model_version=model_version,
        register_model=register_model,
    )


if __name__ == "__main__":
    out = __file__.replace(".py", ".yaml")
    compiler.Compiler().compile(fraud_mlops_pipeline, out)
    print(f"Compiled {out}")
