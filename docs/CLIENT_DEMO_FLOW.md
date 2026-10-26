# Client demo — simple MLOps on RHOAI + Argo CD

## Story (one sentence)

**GitOps syncs the platform → pipeline ingests/processes/trains/saves a model → OVMS serves it in OpenShift AI → TrustyAI monitors bias.**

## Architecture (no extras)

| Step | What | How (RHOAI-standard only) |
|------|------|---------------------------|
| 1 | GitOps | Argo CD `application.yaml` (customer only) |
| 2 | Ingest | KFP step → CSV in S3/MinIO |
| 3 | Features | KFP step → Feast online (fallback to ingest cols) |
| 4 | Train | KFP step → sklearn + MLflow |
| 5 | Save | Same step → `fraud-model.pkl` to S3 |
| 6 | Serve | GitOps: official `kserve-ovms` + demo ONNX on PVC → InferenceService |
| 7 | TrustyAI | `TrustyAIService` + UI Model bias (after a few predicts) |

**Not in this demo:** Flask scorers, custom quay runtimes, sklearn→ONNX conversion, Quay model images.

---

## Customer runbook

Full OCP shell steps: **[CUSTOMER_SHELL.md](CUSTOMER_SHELL.md)**

### A. Platform (once)

```bash
# After bootstrap_gitops.sh / configure_argo_site.sh
oc project fd-gitops
```

### B. Serve model (OVMS — TrustyAI-compatible)

```bash
oc process kserve-ovms -n redhat-ods-applications | oc apply -n fd-gitops -f -
oc apply -f manifests/serving/export-model-job.yaml
oc delete job fd-gitops-seed-onnx -n fd-gitops --ignore-not-found
oc apply -f manifests/serving/seed-onnx-job.yaml
oc wait -n fd-gitops --for=condition=complete job/fd-gitops-seed-onnx --timeout=180s
oc apply -f manifests/serving/fraud-inferenceservice.yaml
oc apply -f manifests/trustyai-service.yaml
oc create route edge fd-gitops-fraud --service=fd-gitops-fraud-predictor --port=http -n fd-gitops --dry-run=client -o yaml | oc apply -f -
oc get isvc fd-gitops-fraud -n fd-gitops   # expect Ready=True, runtime kserve-ovms
```

UI: **Models → Deployments → project `fd-gitops` → `fd-gitops-fraud`** (runtime = OpenVINO Model Server).

### C. Pipeline (ingest → features → train → S3)

```bash
./scripts/run_demo_e2e.sh
# watch
oc get workflow -n fd-gitops -w
```

### D. TrustyAI bias (UI)

1. Send ~20 predicts (UI test **or**):

```bash
HOST=$(oc get route fd-gitops-fraud -n fd-gitops -o jsonpath='{.spec.host}')
TOKEN=$(oc whoami -t)
for i in $(seq 0 29); do
  curl -sk -X POST "https://$HOST/v2/models/fd-gitops-fraud/infer" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"inputs\":[{\"name\":\"input\",\"shape\":[1,6],\"datatype\":\"FP32\",\"data\":[$((20+i)),1.2,1,1,$((i%2)),1]}]}"
done
```

2. **Model bias → Configure** with:

| Field | Value |
|-------|-------|
| Metric name | `spd-ecommerce-channel` |
| Metric type | SPD |
| Protected attribute | `input-4` |
| Privileged value | `0` |
| Unprivileged value | `1` |
| Output | `logits-1` |
| Output value | `0` |
| Violation threshold | `0.1` |
| Metric batch size | `100` |

---

## Repo map

- `pipeline/pipeline.py` — 3 KFP steps  
- `manifests/serving/` — OVMS seed + InferenceService  
- `manifests/trustyai-service.yaml` — TrustyAI CR  
- `feature_repo/` — Feast definitions  
- `argocd/` — Argo Applications  
