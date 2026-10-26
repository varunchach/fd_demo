# Customer deploy — OCP command shell (strict)

No lab path. Real S3 + real Postgres only.

## Before you start

On the customer cluster you need:

- `oc` logged in (cluster-admin or equivalent for GitOps + project create)
- OpenShift GitOps (`openshift-gitops`) installed
- OpenShift AI (RHOAI) with Pipelines + Feature Store operators available
- Customer **S3** endpoint, keys, two buckets (pipeline + feast)
- Customer **PostgreSQL** reachable from the cluster (Feast online)

Clone the repo on a machine that has `oc` (bastion / your laptop):

```bash
git clone https://github.com/varunchach/fd_demo.git
cd fd_demo
chmod +x scripts/*.sh
```

---

## Step 1 — Set site credentials (env only, never commit)

```bash
export AWS_ACCESS_KEY_ID='REPLACE'
export AWS_SECRET_ACCESS_KEY='REPLACE'
export AWS_S3_ENDPOINT='https://REPLACE'    # customer S3 / object store
export AWS_DEFAULT_REGION='us-east-1'
export PIPELINE_BUCKET='REPLACE'            # pipeline artifacts bucket
export FEAST_BUCKET='REPLACE'               # Feast offline / registry bucket

export PG_HOST='REPLACE'
export PG_PORT='REPLACE'                    # e.g. 5432 — REQUIRED, no default
export PG_USER='REPLACE'
export PG_PASSWORD='REPLACE'
export PG_DATABASE='fd_gitops'              # or customer DB name
```

---

## Step 2 — Remove any old lab Application (if present)

```bash
oc delete application fd-gitops -n openshift-gitops --wait=false --ignore-not-found
oc patch application fd-gitops -n openshift-gitops --type merge \
  -p '{"metadata":{"finalizers":null}}' 2>/dev/null || true
oc delete project fd-gitops --wait=false --ignore-not-found
# wait until gone
while oc get ns fd-gitops >/dev/null 2>&1; do echo waiting...; sleep 5; done
```

---

## Step 3 — Create secrets (once)

```bash
./scripts/apply_fd_gitops_secrets.sh
```

Creates in namespace `fd-gitops`:

- `fd-gitops-pipeline-s3`
- `fd-gitops-feast-s3`
- `fd-gitops-feast-pg`

Check:

```bash
oc get secret -n fd-gitops | grep fd-gitops
```

---

## Step 4 — Create Argo Application (customer chart only)

```bash
./scripts/configure_argo_site.sh
```

This:

1. Applies `argocd/application.yaml` (Helm `chart/` + `values.yaml` only — no lab overlay)
2. Patches helm parameters: S3 host, pipeline bucket, feast bucket
3. Triggers sync

Check:

```bash
oc get application fd-gitops -n openshift-gitops
# expect: Synced / Healthy (may take a few minutes)
```

---

## Step 5 — Wait until platform is Ready

```bash
watch -n 10 'oc get application fd-gitops -n openshift-gitops; \
  oc get featurestore fd-gitops-fs -n fd-gitops; \
  oc get dspa -n fd-gitops; \
  oc get svc -n fd-gitops | grep ds-pipeline'
```

Ready when:

- Application: **Synced** + **Healthy**
- FeatureStore `fd-gitops-fs`: **Ready**
- Service: `ds-pipeline-fd-gitops-dspa` exists

---

## Step 6 — Run MLOps path (not Argo)

```bash
./scripts/run_demo_e2e.sh
```

That seeds offline features → materializes online → submits KFP pipeline  
(ingest → features → train → model on S3).

Check:

```bash
oc get workflow -n fd-gitops
# OpenShift AI → project fd-gitops → Pipelines
```

---

## One-shot (steps 3–6 after env is set)

```bash
./scripts/bootstrap_gitops.sh
```

---

## What must NOT be used

| Removed / do not use | Why |
|----------------------|-----|
| `argocd/application-lab.yaml` | deleted — lab MinIO overlay |
| `chart/values-lab.yaml` | deleted |
| `scripts/bootstrap_lab.sh` | deleted |
| Lab Postgres / MinIO templates | deleted |

Only: `argocd/application.yaml` + `chart/values.yaml` + secrets from env.
