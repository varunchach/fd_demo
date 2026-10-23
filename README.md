# Fraud MLOps — GitOps demo (`fd-gitops`)

**Argo = platform. Script = demo run.** That split keeps sync stable.

| Step | Command |
|------|---------|
| Secrets | `./scripts/apply_fd_gitops_secrets.sh` |
| Argo platform | `oc apply -f argocd/application.yaml` then `./scripts/configure_argo_site.sh` |
| Wait | FeatureStore Ready + `ds-pipeline-*` Service |
| Demo | `./scripts/run_demo_e2e.sh` |

Full walkthrough: **[docs/CLIENT_DEMO.md](docs/CLIENT_DEMO.md)**

### Platform (Argo)

- DSPA `fd-gitops-dspa` with **operator-managed MariaDB**
- FeatureStore `fd-gitops-fs` (Postgres online, S3 offline/registry)
- Site buckets via env → `configure_argo_site.sh` (not hardcoded in chart)

### Demo path (script, not Argo hooks)

seed → materialize → submit pipeline
