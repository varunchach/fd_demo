# Serve (RHOAI OVMS only)

```bash
oc process kserve-ovms -n redhat-ods-applications | oc apply -n fd-gitops -f -
oc apply -f manifests/serving/export-model-job.yaml
oc apply -f manifests/serving/seed-onnx-job.yaml
oc apply -f manifests/serving/fraud-inferenceservice.yaml
```

Expect: **Models → Deployments → OpenVINO Model Server**.  
TrustyAI needs this runtime (docs: OVMS only).

Pipeline saves a sklearn pickle to S3 for the train story; live serving uses the demo ONNX on the PVC (same feature vector of 6 floats).
