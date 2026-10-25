# Fraud MLOps — GitOps demo (`fd-gitops`)

**Feast online store is always PostgreSQL** (lab = dummy Postgres container; customer = your PG). Never swapped to Redis.

### Lab / dummy (one apply — Argo syncs platform)

```bash
oc apply -f argocd/application-lab.yaml
# Console: GitOps → Applications → openshift-gitops → fd-gitops
```

### Customer (env once + one script)

```bash
export PIPELINE_BUCKET=... FEAST_BUCKET=... AWS_S3_ENDPOINT=... PG_HOST=... PG_PORT=... PG_USER=... PG_PASSWORD=...
./scripts/bootstrap_gitops.sh
```

**Where to look:** **[docs/WHERE_TO_LOOK.md](docs/WHERE_TO_LOOK.md)** · Details: **[docs/CLIENT_DEMO.md](docs/CLIENT_DEMO.md)**

| Git (Argo) | Lab | Customer |
|------------|-----|----------|
| DSPA + operator MariaDB | `values-lab.yaml` | `configure_argo_site.sh` |
| FeatureStore + **Postgres** | in-cluster PG container | your PG secret |
| S3 secrets | from values-lab | `apply_fd_gitops_secrets.sh` |
