# Fraud MLOps — Argo CD + OpenShift AI 3.5

Simple end-to-end MLOps demo for client showcases:

1. **Pipeline server** declared in Git (DSPA)  
2. **Kubeflow pipeline** with 3 components: S3 ingest → Feature Store → Train / MLflow / Model Registry  
3. **Argo CD** Application keeps the cluster in sync with this repo  

Full click-path: **[ONESHOT.md](ONESHOT.md)**

```
argocd/          Argo CD Application + RBAC
chart/           Helm chart → DSPA, FeatureStore, seed Job, workbench, Model Registry
feature_repo/    Feast definitions (cloned by FeatureStore CR)
pipeline/        KFP v2 source + compiled pipeline.yaml
scripts/         setup-prereqs.sh, install-gitops.sh
```

## Quick deploy (after prereqs)

```bash
./scripts/setup-prereqs.sh --from-secret minio-data-connection --from-ns <your-minio-ns>
./scripts/install-gitops.sh          # if OpenShift GitOps not installed
oc apply -f argocd/gitops-rbac.yaml
oc apply -f argocd/application.yaml
```

## Recompile pipeline

```bash
pip install kfp
python pipeline/pipeline.py
```

## Feature Store modes

| `featureStore.mode` | When |
|---------------------|------|
| `local` (default) | Fastest demo — sqlite/file inside the Feast pods |
| `postgres` | Client already has Postgres + Redis secrets (`feast-*-secret`) |

## What this deliberately skips

Tempo / OpenTelemetry, custom NetworkPolicies, TrustyAI, Redis installs — keep the story on **GitOps → Pipelines → Feature Store → MLflow**.
