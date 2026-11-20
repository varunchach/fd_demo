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

# Optional — Feast feature-repo git remote (defaults to Argo Application source.repoURL)
# export FEAST_GIT_REPO_URL='https://git.customer.example/org/fd_demo.git'
# export FEAST_GIT_REVISION='main'
```

Use a **dedicated Postgres database** if the old stack already uses one.
Set Argo Helm `git.repoURL` to the customer fork (see [FEATURE_STORE_UI.md](FEATURE_STORE_UI.md)).

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

Set the Helm parameter `featureStore.uiEnabled=true` on the chosen Argo Application,
and `featureStore.uiEnabled=false` on the other applications. All applications must
use a chart revision containing this setting. Sync through Argo CD after review.
Do not remove the CR label manually: Argo self-heal restores the Git declaration.

When using the setup script, `FEAST_UI_ENABLED=true` or `false` sets this parameter;
omitting it preserves an existing choice. See [Feature Store UI](FEATURE_STORE_UI.md).

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

