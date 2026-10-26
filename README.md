# Fraud MLOps — customer GitOps (`fd-gitops`)

**Customer only.** Real S3 + real PostgreSQL for Feast online. No lab MinIO, no dummy Postgres.

## What Argo deploys

| Resource | Name |
|----------|------|
| Namespace | `fd-gitops` |
| Argo Application | `fd-gitops` → Helm `chart/` + `values.yaml` |
| DSPA | `fd-gitops-dspa` (operator MariaDB) |
| FeatureStore | `fd-gitops-fs` (Postgres online, S3 offline) |

Site hosts/buckets are **never** committed. Inject via `configure_argo_site.sh`.

## OCP command shell — customer deploy

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
chmod +x scripts/*.sh

# --- your site values (required) ---
export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export AWS_S3_ENDPOINT='https://<customer-s3>'
export AWS_DEFAULT_REGION='us-east-1'
export PIPELINE_BUCKET='...'
export FEAST_BUCKET='...'

export PG_HOST='...'
export PG_PORT='...'          # required — no default
export PG_USER='...'
export PG_PASSWORD='...'
export PG_DATABASE='fd_gitops'

# --- one shot ---
./scripts/bootstrap_gitops.sh
```

Stepped (same result):

```bash
./scripts/apply_fd_gitops_secrets.sh   # 3 secrets
./scripts/configure_argo_site.sh       # Argo Application + helm params + sync
# wait: FeatureStore Ready + ds-pipeline Service
./scripts/run_demo_e2e.sh              # seed → materialize → pipeline
```

**Docs:** [docs/CLIENT_DEMO.md](docs/CLIENT_DEMO.md) · [docs/WHERE_TO_LOOK.md](docs/WHERE_TO_LOOK.md)
