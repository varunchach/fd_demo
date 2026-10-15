"""Fraud-detection KFP v2 pipeline: ingest -> train (+MLflow) -> save & register
(+OpenTelemetry trace). Mirrors the notebook's steps as three pipeline blocks.

Compile with: python pipeline.py  (writes pipeline.yaml)
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


@dsl.component(packages_to_install=["pandas==2.2.3", "scikit-learn==1.5.2"])
def ingest_data(output_data: dsl.Output[dsl.Dataset]):
    """Block 1: Data ingestion. Generates synthetic transaction data."""
    import pandas as pd
    from sklearn.datasets import make_classification

    feature_names = [
        "distance_from_last_transaction",
        "ratio_to_median_purchase_price",
        "used_chip",
        "used_pin_number",
        "online_order",
        "repeat_retailer",
    ]
    X, y = make_classification(
        n_samples=5000,
        n_features=len(feature_names),
        n_informative=4,
        n_redundant=0,
        weights=[0.97, 0.03],
        class_sep=1.2,
        random_state=42,
    )
    df = pd.DataFrame(X, columns=feature_names)
    df["fraud"] = y
    df.to_csv(output_data.path, index=False)
    print(f"Ingested {len(df)} rows, fraud rate {df['fraud'].mean():.2%}")


@dsl.component(packages_to_install=["pandas==2.2.3", "scikit-learn==1.5.2", "mlflow==3.14.0"])
def train_model(
    input_data: dsl.Input[dsl.Dataset],
    model_out: dsl.Output[dsl.Model],
    mlflow_tracking_uri: str,
    mlflow_experiment: str,
):
    """Block 2: Feature processing + split + model building + evaluation + MLflow logging."""
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

    with mlflow.start_run(run_name="kfp-pipeline-run") as run:
        model = LogisticRegression(max_iter=200, class_weight="balanced")
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        accuracy = accuracy_score(y_test, preds)
        precision = precision_score(y_test, preds, zero_division=0)
        recall = recall_score(y_test, preds, zero_division=0)

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
    model_out.metadata["precision"] = precision
    model_out.metadata["recall"] = recall
    print(f"Trained model: accuracy={accuracy:.4f} precision={precision:.4f} recall={recall:.4f}")
    print(f"MLflow run: {run_id}")


@dsl.component(
    packages_to_install=[
        "model-registry==0.2.21",
        "opentelemetry-sdk==1.27.0",
        "opentelemetry-exporter-otlp==1.27.0",
    ]
)
def save_and_register_model(
    model_in: dsl.Input[dsl.Model],
    registry_server_address: str,
    otel_collector_endpoint: str,
    model_name: str,
    model_version: str,
):
    """Block 3: Save/serve step - register the trained model in RHOAI Model
    Registry, wrapped in an OpenTelemetry trace exported to Tempo."""
    from model_registry import ModelRegistry
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": "fraud-detection-pipeline"}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_collector_endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("fraud-detection-pipeline")

    run_id = model_in.metadata.get("mlflow_run_id", "unknown")
    artifact_uri = model_in.metadata.get("mlflow_artifact_uri", "unknown")

    with tracer.start_as_current_span("save-and-register-model") as span:
        span.set_attribute("mlflow.run_id", run_id)
        span.set_attribute("model.accuracy", model_in.metadata.get("accuracy", 0.0))

        registry = ModelRegistry(server_address=registry_server_address, port=443, author="kfp-pipeline")
        version = registry.register_model(
            name=model_name,
            uri=artifact_uri,
            version=model_version,
            model_format_name="sklearn",
            model_format_version="1",
            metadata={
                "mlflow_run_id": run_id,
                "accuracy": model_in.metadata.get("accuracy", 0.0),
                "precision": model_in.metadata.get("precision", 0.0),
                "recall": model_in.metadata.get("recall", 0.0),
            },
        )
        print(f"Registered model {model_name} version {version.id}")

    provider.shutdown()


@dsl.pipeline(name="fraud-detection-pipeline", description="Ingest -> train (+MLflow) -> register (+OTel/Tempo)")
def fraud_detection_pipeline(
    mlflow_tracking_uri: str,
    mlflow_experiment: str = "fraud-detection",
    registry_server_address: str = "https://fraud-detection-registry-rest.apps.example.com",
    otel_collector_endpoint: str = "fraud-otel-collector.fraud-detection.svc.cluster.local:4317",
    model_name: str = "fraud-detection",
    model_version: str = "1.0.0",
):
    ingest_task = ingest_data()

    train_task = train_model(
        input_data=ingest_task.outputs["output_data"],
        mlflow_tracking_uri=mlflow_tracking_uri,
        mlflow_experiment=mlflow_experiment,
    )

    save_and_register_model(
        model_in=train_task.outputs["model_out"],
        registry_server_address=registry_server_address,
        otel_collector_endpoint=otel_collector_endpoint,
        model_name=model_name,
        model_version=model_version,
    )


if __name__ == "__main__":
    compiler.Compiler().compile(fraud_detection_pipeline, __file__.replace(".py", ".yaml"))
    print("Compiled pipeline.yaml")
