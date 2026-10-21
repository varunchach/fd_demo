# One-shot: End-to-end MLOps with Argo CD on OpenShift AI 3.5

Client-facing demo. Three story beats only — no Tempo, no custom policies.

```
Git repo (this)
    │
    ▼
Argo CD Application  ──sync──▶  Namespace fraud-mlops
                                   ├─ DSPA (Pipeline Server)     ← Step 1 story
                                   ├─ FeatureStore (Feast)       ← Step 2 story
                                   ├─ Seed Job → S3 raw CSV
                                   ├─ Workbench (optional)
                                   └─ Model Registry instance
                                         │
                                         ▼
                              KFP run (3 components)
                              1. ingest_from_s3
                              2. process_features (Feast online)
                              3. train_log_register (MLflow ± Registry)
```

---

## Prerequisites (cluster admin, once)

| Item | Check |
|------|--------|
| RHOAI 3.5 | DSC `aipipelines`, `feastoperator`, `mlflowoperator`, `modelregistry`, `workbenches` = **Managed** |
| MLflow | `oc get mlflow` → Available |
| S3 + secrets | You already have MinIO/S3; we create Data Connection secrets |
| Postgres (optional) | Only if Feature Store `mode: postgres` — reuse your feast-* secrets |
| OpenShift GitOps | `./scripts/install-gitops.sh` if `openshift-gitops` ns missing |

---

## Step 0 — Prereqs + GitOps (5 min)

```bash
cd gitops-repo

# A) Namespace + copy existing MinIO data-connection secret
./scripts/setup-prereqs.sh --from-secret minio-data-connection --from-ns credit-decisioning
#    OR set AWS_* env vars and run without --from-*

# B) Install OpenShift GitOps if needed
./scripts/install-gitops.sh

# C) Let Argo CD manage the namespaces
oc apply -f argocd/gitops-rbac.yaml
```

---

## Step 1 — Pipeline server via Argo CD

```bash
oc apply -f argocd/application.yaml
oc get application fraud-mlops -n openshift-gitops
# expect Synced / Healthy

oc get dspa -n fraud-mlops
oc get pods -n fraud-mlops
```

**Client talking point:** *“The pipeline server is declared in Git. Argo CD keeps the cluster matching the repo — that is the CI/CD control plane for ML platform config.”*

---

## Step 2 — Feature Store + Kubeflow pipeline

```bash
# Feature Store clones feature_repo/ from Git and materializes online features
oc get featurestore fraud-feature-store -n fraud-mlops
# phase → Ready

# Import compiled pipeline
# Dashboard → Data Science Pipelines → fraud-mlops → Import pipeline
# File: pipeline/pipeline.yaml
```

Create a run with parameters:

| Parameter | Value |
|-----------|--------|
| `s3_endpoint` | from Secret `my-storage` → `AWS_S3_ENDPOINT` |
| `s3_bucket` | `pipeline-artifacts` (or your bucket) |
| `s3_key` | `fraud-mlops/raw/transactions.csv` |
| `aws_access_key_id` / `aws_secret_access_key` | from Secret `my-storage` |
| `feast_online_server_url` | `http://feast-fraud-feature-store-online.fraud-mlops.svc.cluster.local:80` |
| `mlflow_tracking_uri` | from workbench env / `https://…/mlflow` |
| `register_model` | `false` for first run; `true` + registry URL when registry is Ready |

**Pipeline components (demo narrative):**

1. **Data ingestion (S3)** — pulls raw CSV seeded by the PostSync Job  
2. **Feature processing (Feature Store)** — `get-online-features` from Feast  
3. **Train + MLflow (+ Model Registry)** — metrics/artifacts in MLflow; optional registry

---

## Step 3 — Argo CD as the GitOps loop

Change anything under `chart/` (e.g. workbench memory), push to `main`:

```bash
git add chart && git commit -m "demo: bump workbench memory" && git push
# Argo CD self-heals within ~3 minutes (or click Refresh/Sync)
```

**Client talking point:** *“Platform config is Git-reviewed. Argo CD reconciles — same pattern for DSPA, Feature Store, and registry wiring.”*

---

## Verify success

```bash
# Pipeline run Succeeded in Dashboard
# MLflow experiment fraud-mlops has a run with accuracy/precision/recall
oc get featurestore,dspa -n fraud-mlops
oc get modelregistry -n rhoai-model-registries fraud-mlops-registry
```

---

## Cleanup

```bash
oc delete application fraud-mlops -n openshift-gitops
oc delete ns fraud-mlops
oc delete modelregistry fraud-mlops-registry -n rhoai-model-registries
```

---

## Without Argo CD (lab fallback)

```bash
./scripts/setup-prereqs.sh --from-secret minio-data-connection --from-ns credit-decisioning
helm upgrade --install fraud-mlops ./chart -n fraud-mlops --create-namespace -f chart/values-demo.yaml
```
