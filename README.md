# Fraud Detection MLOps (`fd_demo`)

OpenShift AI 3.5 demo wired for **customer-style stores**:

| Piece | Backend |
|-------|---------|
| Pipeline artifacts | **S3** (`pipeline-artifacts`) |
| Feast offline + registry | **S3** (`feast-offline-s3`) |
| Feast online | **PostgreSQL** (`feast-online-postgres`) |
| DSPA metadata | MySQL/MariaDB (lab chart DB or customer MySQL) |

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
```

**Start here:** [docs/CUSTOMER_DEPLOY.md](docs/CUSTOMER_DEPLOY.md)

Secret templates: [examples/secrets/](examples/secrets/)

```bash
export NS=fraud-mlops
oc new-project $NS
oc label ns $NS opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite
# fill & apply examples/secrets/*.yaml
# edit chart/values.yaml (S3 hosts + registryS3Path)
oc apply -f argocd/application.yaml   # or helm upgrade --install ...
oc apply -f feature_repo/seed-s3-job.yaml
# run pipeline/pipeline.yaml from OpenShift AI → Pipelines
```
