# Fraud Detection MLOps (`fd_demo`)

GitOps demo for **OpenShift AI 3.5**: Feature Store (Feast) → Data Science Pipelines (S3 → Feast → train) → MLflow.

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
```

## What you get

| Component | How |
|-----------|-----|
| Feature Store | `FeatureStore` CR + Feast UI (org catalog) |
| Pipeline server | DSPA + MariaDB |
| 3-step KFP | S3 ingest → Feast online features → train / MLflow |
| GitOps | Argo CD Application under `argocd/` |

## One-time cluster prep

1. **Enable** Feast Operator + Data Science Pipelines in the OpenShift AI dashboard (DataScienceCluster).
2. Create a project (example: `fraud-mlops`) and label it for the dashboard:

```bash
NS=fraud-mlops
oc new-project $NS 2>/dev/null || true
oc label ns $NS opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite
```

3. Create the S3 secret used by DSPA + Feast (MinIO or any S3-compatible endpoint):

```bash
oc create secret generic pipeline-artifacts -n $NS \
  --from-literal=AWS_ACCESS_KEY_ID='<key>' \
  --from-literal=AWS_SECRET_ACCESS_KEY='<secret>' \
  --from-literal=AWS_S3_ENDPOINT='http://minio.<ns>.svc.cluster.local:9000' \
  --from-literal=AWS_S3_BUCKET='pipeline-artifacts' \
  --from-literal=AWS_DEFAULT_REGION='us-east-1' \
  --dry-run=client -o yaml | oc apply -f -
```

4. Edit `chart/values.yaml` (`pipelines.s3Host`, `s3Bucket`, etc.) to match that endpoint.

## Deploy (GitOps — recommended)

```bash
# Point Argo at this repo / namespace (edit argocd/application.yaml if needed)
oc apply -f argocd/application.yaml
# Or sync an existing Application named fraud-mlops in openshift-gitops
```

Wait until DSPA + FeatureStore are Ready:

```bash
oc get dspa,featurestore -n fraud-mlops
```

## Deploy (Helm — same chart)

```bash
helm upgrade --install fraud-mlops ./chart -n fraud-mlops --create-namespace
```

## Seed Feast offline parquet (required once)

```bash
# Uses secret pipeline-artifacts (same keys as above)
oc apply -f feature_repo/seed-s3-job.yaml
# If namespace differs, edit metadata.namespace in the YAML first
oc wait -n fraud-mlops --for=condition=complete job/seed-features-to-s3 --timeout=300s
```

Optional: write online features + FeatureService/Dataset helpers:

```bash
# After FeatureStore pod is Running
./scripts/bootstrap-feast.sh   # Linux/Mac
# or: oc apply helpers in scripts/ (see scripts/README)
```

## Upload & run the pipeline

```bash
# Compile (optional — pipeline/pipeline.yaml is committed)
pip install 'kfp==2.17.0'
python pipeline/pipeline.py

# Load YAML into the cluster ConfigMap used by the submit Job
oc create configmap fraud-mlops-pipeline-yaml -n fraud-mlops \
  --from-file=pipeline.yaml=pipeline/pipeline.yaml \
  --dry-run=client -o yaml | oc apply -f -

oc create configmap feast-submit-script -n fraud-mlops \
  --from-file=submit_pipeline_run.py=scripts/submit_pipeline_run.py \
  --dry-run=client -o yaml | oc apply -f -

# One-time: DSPA API access for the submitter SA
oc apply -f scripts/submitter-rbac.yaml

oc delete job submit-fraud-pipeline -n fraud-mlops --ignore-not-found
oc apply -f scripts/submit-fraud-pipeline-job.yaml
oc logs -f -n fraud-mlops -l job-name=submit-fraud-pipeline
```

Or run from **OpenShift AI → Pipelines** (project `fraud-mlops`, DSPA `fraud-detection-dspa`).

### Pipeline parameters (defaults)

| Param | Example |
|-------|---------|
| `s3_endpoint` / bucket / keys | From `pipeline-artifacts` secret |
| `feast_online_server_url` | `https://feast-fraud-feature-store-online.fraud-mlops.svc.cluster.local:443` |
| `mlflow_tracking_uri` | `https://mlflow.redhat-ods-applications.svc.cluster.local:8443/mlflow` |

Train step uses RHOAI workspace auth (`MLFLOW_WORKSPACE` + `kubernetes-namespaced`) via `KFP_MLFLOW_CONFIG` injected by DSPA.

## Feature Store UI

- Label on the CR: `feature-store-ui: enabled` (only one store in the org should have this).
- Registry REST API must be enabled (`spec.services.registry.local.server.restAPI: true`) — already in `chart/templates/featurestore.yaml`.
- Dashboard: **Develop & train → Feature store** (org-scoped).

## Repo layout

```
argocd/           Argo CD Application
chart/            Helm: DSPA, MariaDB, FeatureStore
feature_repo/     Feast definitions (pulled by FeatureStore git)
pipeline/         KFP source + compiled YAML
scripts/          Seed, submit run, Feast helpers
```

## Verify

```bash
oc get featurestore,dspa -n fraud-mlops
oc get workflow -n fraud-mlops   # expect Succeeded after a run
```
