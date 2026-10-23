# Fraud MLOps — GitOps demo (`fd-gitops`)

**Argo syncs platform from Git. Demo run is an explicit script after Ready.**

```bash
export AWS_* PIPELINE_BUCKET FEAST_BUCKET PG_*   # site config
./scripts/bootstrap_gitops.sh                    # secrets → Argo → e2e
```

Or: `apply_fd_gitops_secrets.sh` → `configure_argo_site.sh` → wait → `run_demo_e2e.sh`

Details / learnings: **[docs/CLIENT_DEMO.md](docs/CLIENT_DEMO.md)**

| Git (Argo) | Not in Argo hooks |
|------------|-------------------|
| DSPA + **managed MariaDB** (`Replace=true`) | seed / materialize / submit |
| FeatureStore + S3/Postgres wiring | (`run_demo_e2e.sh`) |
| Site buckets via helm.parameters | |
