# Client demo script — secrets → Argo → full MLOps run

**Story:** declare the platform in Git; Argo CD syncs it; PostSync hooks seed Feast, materialize online features, and submit a training pipeline — no dashboard click-ops.

**Namespace (greenfield):** `fd-gitops`  
*(Leave `fraud-mlops` / older projects alone for comparison.)*

Repo: `https://github.com/varunchach/fd_demo`

---

## Demo outline (what to say + what to click)

| Step | You show | Talking point |
|------|----------|----------------|
| 0 | Empty / new project `fd-gitops` | Fresh namespace — not reusing old DSPA |
| 1 | 3 Secrets | Dual S3 (pipeline vs features) + Postgres online store |
| 2 | GitOps → Applications → `fd-gitops` | Desired state = Git (`chart/`) |
| 3 | Sync waves / Jobs | Seed → materialize → submit |
| 4 | Feature Store UI | Features on registry (creds on UI/registry/online) |
| 5 | Pipeline Workflow Succeeded | S3 → Feast online → train / MLflow |
| 6 | MLflow experiment `fd-gitops-training` | Metrics logged from train step |

---

## Before the room (once)

1. OpenShift GitOps installed (you already have it).
2. OpenShift AI: Data Science Pipelines + Feast (+ MLflow) enabled.
3. Create **two S3 buckets** (same account/keys as lab is fine):
   - `fd-gitops-pipeline`
   - `fd-gitops-features`
4. Create a **fresh Postgres DB** (e.g. database `fd_gitops`) — do not reuse old Feast online data.
5. Clone repo and set S3 host + registry path in values:

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
# edit chart/values.yaml:
#   pipelines.s3Host: <hostname only, no https://>
#   pipelines.s3Bucket: fd-gitops-pipeline
#   featureStore.registryS3Path: s3://fd-gitops-features/fd-gitops/registry.db
git add chart/values.yaml && git commit -m "demo: set customer S3 host/buckets" && git push
```

---

## Step 1 — Secrets (one command)

Same S3 **keys + endpoint** as your working lab secret; **only bucket names** change. Postgres is **new**.

```bash
cd fd_demo
chmod +x scripts/apply_fd_gitops_secrets.sh scripts/verify_feast_registry.sh

export PG_HOST='<postgres-host>'
export PG_PORT='6666'                          # REQUIRED — your port (not assumed 5432)
export PG_USER='<user>'
export PG_PASSWORD='<password>'
export PG_DATABASE='fd_gitops'                 # fresh DB
export PIPELINE_BUCKET='fd-gitops-pipeline'
export FEAST_BUCKET='fd-gitops-features'
# copies keys from fraud-mlops/feast-offline-s3 by default:
export SRC_NS='fraud-mlops' SRC_SECRET='feast-offline-s3'

./scripts/apply_fd_gitops_secrets.sh
```

Confirm port landed in the secret:

```bash
oc get secret fd-gitops-feast-pg -n fd-gitops \
  -o jsonpath='{.data.feature_store\.yaml}' | base64 -d | grep -E '^(host|port|database|user):'
# port: 6666
```

### Offline + registry checklist (before / after Argo)

| Must match | Where |
|------------|--------|
| Feast bucket name | Secret `fd-gitops-feast-s3` → `AWS_S3_BUCKET` **and** `chart/values.yaml` → `featureStore.registryS3Path` (`s3://<same-bucket>/fd-gitops/registry.db`) |
| Offline parquet prefix | `featureStore.offlineS3Prefix` (`fd-gitops/features`) = seed Job + `features.py` FileSource |
| Endpoint for Feast/boto3 | Secret has **`AWS_ENDPOINT_URL`** (not only `AWS_S3_ENDPOINT`) |
| Registry + UI creds | Chart already sets `envFrom` on **online, registry, ui** → `fd-gitops-feast-s3` (no manual patch) |

```bash
# After FeatureStore exists (post Argo sync):
./scripts/verify_feast_registry.sh
# All OK = bucket matches registry path + envFrom on online/registry/ui + Ready
```

Verify secrets exist:

```bash
oc get secret -n fd-gitops
# fd-gitops-pipeline-s3  fd-gitops-feast-s3  fd-gitops-feast-pg
```

**Client line:** “Credentials stay out of Git; Git only references secret *names*.”

---

## Step 2 — Register Argo Application

```bash
oc apply -f argocd/application.yaml
```

UI path:

1. OpenShift console → **GitOps** → **Applications**
2. Open **`fd-gitops`** (or Argo CD route):

```bash
oc get route openshift-gitops-server -n openshift-gitops \
  -o jsonpath='https://{.spec.host}{"\n"}'
```

**Client line:** “Application points at Git `chart/`; destination namespace `fd-gitops`. Auto-sync + self-heal.”

---

## Step 3 — Watch the GitOps execution

```bash
oc get application fd-gitops -n openshift-gitops -w
# Healthy / Synced

oc get featurestore,dspa -n fd-gitops
oc get jobs -n fd-gitops

oc logs -n fd-gitops -l job-name=fd-gitops-seed-offline --tail=30
oc logs -n fd-gitops -l job-name=fd-gitops-materialize-online --tail=40
# expect: write_to_online_store=OK

oc logs -n fd-gitops -l job-name=fd-gitops-submit-pipeline --tail=40
# expect: run_id ...

oc get workflow -n fd-gitops -w
```

**Sync order to narrate:**

```
wave 0  MariaDB fd-gitops-db
wave 1  DSPA fd-gitops-dspa
wave 2  FeatureStore fd-gitops-fs   (online+registry+UI get feast S3 envFrom)
PostSync 10  seed parquet → S3
PostSync 20  materialize → Postgres online
PostSync 30  upload pipeline + create run
```

---

## Step 4 — Feature Store (UI)

OpenShift AI → project **`fd-gitops`** → Feature Store **`fd-gitops-fs`**.

Show feature views / feature service populated (registry reachable because UI has AWS env).

---

## Step 5 — Pipeline + MLflow

- OpenShift AI → Pipelines / Runs in `fd-gitops`, or  
  `oc get workflow -n fd-gitops` → all steps Succeeded  
- MLflow → experiment **`fd-gitops-training`** → run metrics (accuracy / precision / recall)

**Client line:** “End-to-end: object storage → feature store (online) → training → experiment tracking, driven by GitOps.”

---

## Step 6 — Tear down (optional)

```bash
oc delete application fd-gitops -n openshift-gitops
# oc delete project fd-gitops
```

`fraud-mlops` remains untouched.

---

## If you want a *different* namespace name

Today the chart/Application default to `fd-gitops`. To rename for a named customer demo:

1. Change `argocd/application.yaml` `destination.namespace` + RoleBinding namespace  
2. Change secret apply `-n` / `NS=`  
3. Keep resource names (`fd-gitops-dspa`, etc.) or rename in `chart/values.yaml`  
4. Commit + push, then `oc apply -f argocd/application.yaml`

---

## Fail-fast checklist

| Symptom | Fix |
|---------|-----|
| Application Unknown/Missing | GitOps operator / `oc apply -f argocd/application.yaml` |
| FeatureStore not Ready / NoCredentials | Secret `fd-gitops-feast-s3` must have `AWS_ENDPOINT_URL` + keys; chart already wires envFrom on registry/UI/online |
| Materialize fails | Seed Job must finish first; Postgres secret must be **flat** YAML |
| Submit can’t reach DSPA | Wait for Service `ds-pipeline-fd-gitops-dspa` |
| Train NaNs | Materialize must print `write_to_online_store=OK` before submit |
