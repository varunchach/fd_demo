# Fraud Detection MLOps (OpenShift AI 3.5)

GitOps demo: **S3 → Feast Feature Store → train / MLflow** in namespace `fraud-detection`.

| Layer | What |
|-------|------|
| Helm chart / Argo CD | DSPA + FeatureStore (Postgres online, S3 offline+registry) |
| Secrets | `pipeline-artifacts`, `feast-offline-s3`, `feast-online-postgres` |
| `scripts/oneshot.sh` | Seed parquet + submit pipeline run (CLI) |

## Quick start

See **[docs/ONESHOT.md](docs/ONESHOT.md)**.

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
# fill examples/secrets/*.yaml + chart/values.yaml
oc apply -f examples/secrets/ -n fraud-detection
./scripts/oneshot.sh
```

## Architecture

- Pipeline artifacts S3 → secret `pipeline-artifacts`
- Feast offline + registry S3 → secret `feast-offline-s3` (flat `AWS_*` + `AWS_ENDPOINT_URL`)
- Feast online Postgres → secret `feast-online-postgres` (**flat** YAML under key `feature_store.yaml`, no `online_store:` wrapper)
- DSPA metadata DB → chart MariaDB (`deployMariaDB: true`)
