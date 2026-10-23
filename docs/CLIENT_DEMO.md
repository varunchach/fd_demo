# Client demo — robust GitOps path

## Design (why this won’t thrash)

| Layer | Owned by | What |
|-------|----------|------|
| Platform | **Argo CD** | DSPA + managed MariaDB + FeatureStore + RBAC |
| Site config | **env → configure_argo_site.sh** | S3 host/buckets (not hardcoded in Git) |
| Demo run | **run_demo_e2e.sh** | seed → materialize → submit (after platform Ready) |

Argo PostSync Jobs are **disabled**. They previously blocked sync when DSPA/DB lagged, which made working Feast look “broken”.

Namespace: `fd-gitops`

---

## One clean sequence

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
chmod +x scripts/*.sh

export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export AWS_S3_ENDPOINT='https://YOUR_S3_HOST'
export AWS_DEFAULT_REGION='us-east-1'
export PIPELINE_BUCKET='kubeflow-pipelines'
export FEAST_BUCKET='feature-store'

export PG_HOST='...'
export PG_PORT='6666'
export PG_USER='...'
export PG_PASSWORD='...'
export PG_DATABASE='featurestore'

# 1) Secrets
./scripts/apply_fd_gitops_secrets.sh

# 2) Argo Application (platform only)
oc apply -f argocd/application.yaml
./scripts/configure_argo_site.sh

# 3) Wait until platform is healthy
oc get featurestore fd-gitops-fs -n fd-gitops -w          # Ready
oc get svc -n fd-gitops | grep ds-pipeline                 # must exist
oc get pods -n fd-gitops                                   # feast + mariadb + ds-pipeline-*

# 4) Demo path (NOT Argo)
./scripts/run_demo_e2e.sh
oc get workflow -n fd-gitops -w
```

---

## What to show the client

1. **GitOps → Applications → `fd-gitops`** — Synced/Healthy (platform)
2. **Feature Store** UI in project `fd-gitops`
3. After `run_demo_e2e.sh` — Workflow Succeeded + MLflow `fd-gitops-training`

---

## Do not

- Put seed/submit as Argo PostSync hooks (re-enabled only if you accept sync risk)
- Hand-edit DSPA while Argo manages it — fix Git / helm.parameters instead
- Skip `configure_argo_site.sh` (buckets must match secrets)

---

## Tear down

```bash
oc delete applications.argoproj.io fd-gitops -n openshift-gitops
oc delete project fd-gitops
```
