# Client demo — synced GitOps workflow (final)

## Architecture

| Layer | Source of truth | How |
|-------|-----------------|-----|
| DSPA + managed MariaDB + Feast | **Git** `chart/` | Argo Application `fd-gitops` |
| S3 host / buckets | **env** (not committed) | `configure_argo_site.sh` → helm.parameters |
| Secrets | cluster (once) | `apply_fd_gitops_secrets.sh` |
| seed → materialize → submit | script after Ready | `run_demo_e2e.sh` |

**No manual `oc apply` DSPA YAML.** Chart has `mariaDB.deploy: true`, `tls: false`, and `argocd.argoproj.io/sync-options: Replace=true` so stale `externalDB` cannot stick.

Demo Jobs are **not** Argo PostSync hooks (hooks stay off so sync never hangs).

---

## Learnings baked into Git

1. Feast registry/UI/online get `envFrom` feast S3 secret (chart FeatureStore).
2. Registry path = `s3://$FEAST_BUCKET/fd-gitops/registry.db` from helm param (not hardcoded).
3. Postgres port is required env (`PG_PORT`), e.g. `6666`.
4. DSPA uses **operator MariaDB**, not a DIY Deployment (`:3306` timeouts).
5. MLflow mode `AUTODETECT` (uppercase enum).
6. Materialize uses `oc exec` stdin (Feast image has no `tar` for `oc cp`).
7. Pipeline run is `run_demo_e2e.sh` after `ds-pipeline-*` Service exists.

---

## Demo commands (greenfield or re-sync)

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
git reset --hard origin/main
chmod +x scripts/*.sh

export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export AWS_S3_ENDPOINT='https://bls3-rhoat-non-prod.bajajlife.com'
export AWS_DEFAULT_REGION='us-east-1'
export PIPELINE_BUCKET='kubeflow-pipelines'
export FEAST_BUCKET='feature-store'

export PG_HOST='...'
export PG_PORT='6666'
export PG_USER='...'
export PG_PASSWORD='...'
export PG_DATABASE='featurestore'

# One shot:
./scripts/bootstrap_gitops.sh

# Or stepped:
# ./scripts/apply_fd_gitops_secrets.sh
# ./scripts/configure_argo_site.sh          # oc apply Application + params + sync
# # wait FeatureStore Ready + ds-pipeline Service
# ./scripts/run_demo_e2e.sh
```

---

## Re-enable Argo after an earlier manual freeze

If you had set `syncPolicy: null` during troubleshooting:

```bash
# same AWS_* / bucket exports
./scripts/configure_argo_site.sh
```

That re-applies `argocd/application.yaml` (automated sync) and syncs DSPA from Git with Replace.

---

## Client talking points

1. GitOps → Applications → `fd-gitops` — Synced (platform from Git).
2. Feature Store Ready; pipeline Services present.
3. `run_demo_e2e.sh` — Workflow Succeeded; MLflow experiment `fd-gitops-training`.
