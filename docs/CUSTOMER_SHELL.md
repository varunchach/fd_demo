# Customer deploy — new namespace (safe, parallel)

Leaves any existing `fd-gitops` stack alone. Creates a **new** project + Argo Application.

Recommended names (change if you want):

```bash
export NS=fd-cust
export APP_NAME=fd-cust
```

Resource names inside the chart stay `fd-gitops-dspa` / `fd-gitops-fs` / secrets `fd-gitops-*` — they are isolated by **namespace**.

---

## Step 1 — Clone

```bash
git clone https://github.com/varunchach/fd_demo.git
cd fd_demo
git pull origin main
chmod +x scripts/*.sh
```

## Step 2 — Credentials + new stack names

```bash
export NS=fd-cust
export APP_NAME=fd-cust

export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export AWS_S3_ENDPOINT='https://<customer-s3>'
export AWS_DEFAULT_REGION='us-east-1'
export PIPELINE_BUCKET='...'
export FEAST_BUCKET='...'

export PG_HOST='...'
export PG_PORT='...'
export PG_USER='...'
export PG_PASSWORD='...'
export PG_DATABASE='fd_gitops'    # or a dedicated DB for this stack
```

Use a **dedicated Postgres database** if the old stack already uses one.

## Step 3 — Secrets (new namespace only)

```bash
./scripts/apply_fd_gitops_secrets.sh
oc get secret -n "$NS" | grep fd-gitops
```

## Step 4 — Argo Application (new name → new NS)

```bash
./scripts/configure_argo_site.sh
oc get application "$APP_NAME" -n openshift-gitops
```

Does **not** delete or sync the old `fd-gitops` app.

## Step 5 — Feature Store UI label (cluster rule)

Only **one** FeatureStore cluster-wide may have `feature-store-ui=enabled`.

If old stack still has the UI:

```bash
oc label featurestore fd-gitops-fs -n fd-gitops feature-store-ui- --overwrite
```

## Step 6 — Wait Ready

```bash
oc get application "$APP_NAME" -n openshift-gitops
oc get featurestore fd-gitops-fs -n "$NS"
oc get dspa -n "$NS"
oc get svc -n "$NS" | grep ds-pipeline
```

## Step 7 — Pipeline

```bash
NS="$NS" FS_NAME=fd-gitops-fs DSPA_NAME=fd-gitops-dspa ./scripts/run_demo_e2e.sh
oc get workflow -n "$NS"
```

## One-shot (after Step 2 exports)

```bash
./scripts/bootstrap_gitops.sh
```

---

## What stays untouched

| Old | New |
|-----|-----|
| ns `fd-gitops` | ns `$NS` (e.g. `fd-cust`) |
| Argo app `fd-gitops` | Argo app `$APP_NAME` |
| (optional wipe) | **no wipe** |
