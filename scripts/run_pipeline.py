import kfp

client = kfp.Client(
    host="https://ds-pipeline-pipelines-definition.fraud-detection.svc.cluster.local:8888",
    ssl_ca_cert="/var/run/secrets/kubernetes.io/serviceaccount/service-ca.crt",
)

run = client.create_run_from_pipeline_package(
    pipeline_file="5_get_data_train_upload.yaml",
    run_name="fraud-detection-run-3",
    experiment_name="fraud-detection",
)
print("Run submitted:", run.run_id)
