# Fraud MLOps — Argo CD + OpenShift AI 3.5

Minimal end-to-end MLOps demo:

```
Git (this repo) --Argo CD--> DSPA + FeatureStore
                              |
                              v
                     KFP: S3 -> Feast -> Train/MLflow
```

## Clone

```bash
git clone https://github.com/varunchach/fd_demo.git
cd fd_demo
```

## Layout (final)

```
argocd/application.yaml   # Argo CD App + RBAC
chart/                    # DSPA + FeatureStore only
feature_repo/             # Feast definitions (cloned by operator)
pipeline/                 # 3-step KFP source + compiled YAML
```

## One-shot deploy

**0. Prereqs:** RHOAI 3.5 with `aipipelines`, `feastoperator`, `mlflowoperator` Managed. OpenShift GitOps installed. MLflow Available (`oc get mlflow`).

**1. Namespace + S3 secrets** (you already have MinIO — copy a data-connection secret):

```bash
oc create ns fraud-mlops
oc label ns fraud-mlops opendatahub.io/dashboard=true --overwrite

# Copy your existing MinIO data connection (adjust names/ns)
oc get secret minio-data-connection -n credit-decisioning -o json \
  | sed 's/"namespace":"[^"]*"/"namespace":"fraud-mlops"/; s/"name":"[^"]*"/"name":"pipeline-artifacts"/' \
  | oc apply -f -
# Ensure AWS_S3_BUCKET=pipeline-artifacts and host matches chart/values.yaml
```

**2. Argo CD sync:**

```bash
oc apply -f argocd/application.yaml
oc get application fraud-mlops -n openshift-gitops   # Synced/Healthy
oc get dspa,featurestore -n fraud-mlops             # FeatureStore Ready
```

**3. Run pipeline:** Dashboard → Pipelines → Import `pipeline/pipeline.yaml` → Create run.

| Param | Example |
|-------|---------|
| `s3_endpoint` | from Secret `pipeline-artifacts` / `AWS_S3_ENDPOINT` |
| `s3_bucket` | `pipeline-artifacts` |
| `aws_access_key_id` / `aws_secret_access_key` | from same Secret |
| `feast_online_server_url` | `https://feast-fraud-feature-store-online.fraud-mlops.svc.cluster.local:443` |
| `mlflow_tracking_uri` | cluster MLflow URL (e.g. `https://mlflow.redhat-ods-applications.svc:8443/mlflow`) |

Pipeline steps: **(1) S3 ingest** (auto-seeds CSV if missing) → **(2) Feast online features** → **(3) train + MLflow** (set `registry_server_address` only if you want Model Registry).

## Helm fallback (no Argo CD)

```bash
helm upgrade --install fraud-mlops ./chart -n fraud-mlops --create-namespace
```

## Recompile pipeline

```bash
pip install kfp && python pipeline/pipeline.py
```

## Cleanup

```bash
oc delete application fraud-mlops -n openshift-gitops
oc delete ns fraud-mlops
```
