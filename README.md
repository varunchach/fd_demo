# Fraud Detection MLOps — GitOps / Argo CD demo (OpenShift AI 3.5)

**S3 → Feast (Postgres online) → DSPA train / MLflow** in namespace `fraud-detection`.

| Layer | What |
|-------|------|
| **Argo CD** | Syncs `chart/` → DSPA + FeatureStore + PostSync Jobs |
| **PostSync hooks** | Seed parquet → materialize online → submit pipeline run |
| **Secrets** (once) | `pipeline-artifacts`, `feast-offline-s3`, `feast-online-postgres` |

## Start here

**GitOps / Argo path (recommended):** **[docs/GITOPS_DEMO.md](docs/GITOPS_DEMO.md)**

**CLI without Argo:** **[docs/ONESHOT.md](docs/ONESHOT.md)** → `./scripts/oneshot.sh`

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
# fill examples/secrets/*.yaml + chart/values.yaml
oc apply -f examples/secrets/ -n fraud-detection
oc apply -f argocd/application.yaml
```

## Architecture

- Pipeline artifacts S3 → secret `pipeline-artifacts`
- Feast offline + registry S3 → secret `feast-offline-s3` (`AWS_ENDPOINT_URL` + checksums)
- Feast online Postgres → secret `feast-online-postgres` (**flat** YAML under `feature_store.yaml`)
- DSPA metadata → chart MariaDB (`deployMariaDB: true`) or existing DB
- MLflow → `integrationMode: Disabled` (SDK logs from train step)

## Existing DSPA named `dspa`

```bash
helm upgrade --install fraud-detection ./chart -n fraud-detection \
  -f chart/values.yaml -f chart/values-customer-existing-dspa.yaml
```
