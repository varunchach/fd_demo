"""Register the trained fraud-detection model (produced by the official tutorial
notebook) into the RHOAI Model Registry."""
from model_registry import ModelRegistry

registry = ModelRegistry(
    server_address="https://fraud-detection-registry-rest.apps.ocp.ztpwc.sandbox1039.opentlc.com",
    port=443,
    author="rhoai-fraud-demo",
)

model = registry.register_model(
    name="fraud-detection",
    uri="s3://my-storage/models/fraud/1/model.onnx",
    version="1.0.0",
    model_format_name="onnx",
    model_format_version="1",
    description="Fraud detection model from the official RHOAI tutorial (keras NN -> ONNX), trained in the fraud-detection workbench.",
    metadata={
        "accuracy_pct": 97.5145,
        "precision": 0.9715088892265613,
        "recall": 0.7356037507910027,
        "mlflow_run_id": "0496652366584bcca77c3983a9c56a12",
    },
)
print("Registered model:", model.id, model.name)
