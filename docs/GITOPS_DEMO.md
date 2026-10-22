# GitOps / Argo CD demo — Fraud MLOps on OpenShift AI

End-to-end **GitOps-styled** demo: declare platform in Git, sync with Argo CD, and let **PostSync hooks** seed Feast, materialize online features, and submit a DSPA pipeline run.

Namespace: **`fraud-detection`**  
Repo: `https://github.com/varunchach/fd_demo.git`

---

## What Git owns vs what you apply once

| Once (out of band) | Git / Argo CD |
|--------------------|---------------|
| Secrets: `pipeline-artifacts`, `feast-offline-s3`, `feast-online-postgres` | Helm chart: MariaDB (DSPA meta), DSPA, FeatureStore |
| OpenShift GitOps operator + `argocd/application.yaml` RoleBinding | PostSync Jobs: seed → materialize → submit |
| RHOAI components enabled in dashboard (DSP, Feast) | Pipeline YAML + submit script as ConfigMaps |

Secrets are **never** committed with real credentials — only `examples/secrets/*.yaml` placeholders.

---

## Sync waves (Argo CD)

```
wave 0   MariaDB (DSPA metadata) + fraud-db Secret
wave 1   DataSciencePipelinesApplication
wave 2   FeatureStore (Postgres online + S3 offline/registry)
wave 3   submitter SA/RBAC + ConfigMaps (scripts)
────────────────────────────────────────────────
PostSync 10  gitops-seed-feast-offline     (parquet → S3)
PostSync 20  gitops-materialize-feast-online (S3 → Postgres online via Feast pod)
PostSync 30  gitops-submit-fraud-pipeline  (upload KFP + create run)
```

Hooks use `hook-delete-policy: BeforeHookCreation` so each sync re-runs the demo path cleanly.

---

## Demo flow (customer / lab)

### 1. Fill secrets + chart values

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo

# Replace REPLACE_ME / hosts / buckets
vi examples/secrets/pipeline-artifacts.yaml
vi examples/secrets/feast-offline-s3.yaml      # AWS_ENDPOINT_URL + checksums
vi examples/secrets/feast-online-postgres.yaml # FLAT host/db/user/password under feature_store.yaml

vi chart/values.yaml   # pipelines.s3Host, s3Bucket, featureStore.registryS3Path
```

### 2. Create namespace + secrets

```bash
oc new-project fraud-detection 2>/dev/null || oc project fraud-detection
oc label ns fraud-detection opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite
oc apply -f examples/secrets/ -n fraud-detection
```

### 3. Point Argo at this repo

```bash
oc apply -f argocd/application.yaml
# Application: fraud-detection  (openshift-gitops)
# Watches chart/ on main → namespace fraud-detection
```

Or helm without Argo (same chart, same hooks as Jobs you can also apply manually):

```bash
helm upgrade --install fraud-detection ./chart -n fraud-detection
```

### 4. Watch the GitOps path

```bash
# Argo UI or:
oc get application fraud-detection -n openshift-gitops -w

# After sync Healthy:
oc get jobs -n fraud-detection | grep gitops
oc logs -n fraud-detection -l job-name=gitops-seed-feast-offline --tail=30
oc logs -n fraud-detection -l job-name=gitops-materialize-feast-online --tail=40
oc logs -n fraud-detection -l job-name=gitops-submit-fraud-pipeline --tail=40
oc get workflow -n fraud-detection
```

### 5. Existing DSPA named `dspa`

If the project already has DSPA `dspa` (Service `ds-pipeline-dspa`):

```bash
helm upgrade --install fraud-detection ./chart -n fraud-detection \
  -f chart/values.yaml -f chart/values-customer-existing-dspa.yaml
```

That sets `pipelines.enabled: false` and points submit at `ds-pipeline-dspa`.

---

## Architecture (learnings baked in)

- **Dual S3**: `pipeline-artifacts` (DSPA / raw CSV) ≠ `feast-offline-s3` (parquet + registry)
- **Feast online**: Postgres via **flat** secret key `feature_store.yaml` (no `online_store:` wrapper)
- **Feast pods**: `envFrom` feast-offline-s3 on online / registry / UI + checksum env vars
- **Materialize**: `write_to_online_store` inside Feast **online** container (avoids empty online → NaN in train)
- **MLflow**: DSPA `mlflow.integrationMode: Disabled` (SDK logging in train step; avoids nested-run plugin 409)
- **Submit URL**: `https://ds-pipeline-<dspaName>.<ns>.svc.cluster.local:8443` (not a non-existent Helm Service name)

---

## Toggle hooks

```yaml
# chart/values.yaml
hooks:
  enabled: true
  seedOffline: true
  materializeOnline: true
  submitPipeline: false   # platform sync only; submit later via Job
```

Manual submit after platform is Ready:

```bash
oc delete job gitops-submit-fraud-pipeline -n fraud-detection --ignore-not-found
# Re-sync Argo with submitPipeline: true, or:
oc apply -f scripts/submit-fraud-pipeline-job.yaml -n fraud-detection
```

---

## Verify success

| Check | Expect |
|-------|--------|
| FeatureStore | `status.phase=Ready` |
| Seed Job | `Uploaded s3://.../transactions.parquet` |
| Materialize | `write_to_online_store=OK` + sample features |
| Submit Job | `run_id ...` |
| Workflow | Succeeded; train step has non-NaN metrics in MLflow |

---

## Repo map

```
argocd/application.yaml     Argo Application + GitOps SA RoleBinding
chart/                      Helm: DSPA, Feast, MariaDB, PostSync hooks
chart/files/                Scripts/YAML embedded into ConfigMaps
feature_repo/               Feast definitions (FeatureStore git source)
pipeline/                   KFP source + compiled pipeline.yaml
examples/secrets/           Placeholder secrets
scripts/oneshot.sh          Non-Argo path (helm + seed Job + submit Job)
docs/ONESHOT.md             Short CLI path
docs/GITOPS_DEMO.md         This file
```
