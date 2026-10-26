# 30-minute client demo (MLOps only)

## What you show

1. **Argo CD** — `fd-gitops` Synced/Healthy  
2. **Models** — `fd-gitops-fraud` Ready (OpenVINO Model Server)  
3. **Pipelines** — run: ingest → features → train → model on S3  
4. **Feature Store** — `fraud_txn_risk_signals` (optional glance)

Skip TrustyAI for this slot.

## Live commands

```bash
oc project fd-gitops

# Model (already up)
oc get isvc fd-gitops-fraud
# Predict
HOST=$(oc get route fd-gitops-fraud -o jsonpath='{.spec.host}')
curl -sk -X POST "https://$HOST/v2/models/fd-gitops-fraud/infer" \
  -H "Authorization: Bearer $(oc whoami -t)" -H "Content-Type: application/json" \
  -d '{"inputs":[{"name":"input","shape":[1,6],"datatype":"FP32","data":[20,1.2,1,1,0,1]}]}'

# Pipeline
./scripts/run_demo_e2e.sh
oc get workflow -n fd-gitops -w
```

## UI path

OpenShift AI → project **fd-gitops**  
→ **Models / Deployments** → `fd-gitops-fraud`  
→ **Develop & train / Pipelines** → latest run (Succeeded)

## Talking points (30 sec each)

- GitOps owns platform YAML (Argo), not click-ops  
- Pipeline: S3 ingest → Feast features → train + MLflow → pickle on S3  
- Serve: RHOAI KServe OVMS InferenceService from Git  
