# One-shot deploy (GitOps)

Namespace: **fraud-detection**. Everything lives in this repo — no ad-hoc `sed`.

## Once: fill secrets + chart values

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo

# edit REPLACE_ME / hosts / buckets
vi examples/secrets/pipeline-artifacts.yaml
vi examples/secrets/feast-offline-s3.yaml      # include AWS_ENDPOINT_URL + checksums
vi examples/secrets/feast-online-postgres.yaml # FLAT host/database/user/password (no online_store:)

vi chart/values.yaml   # pipelines.s3Host/s3Bucket + featureStore.registryS3Path

oc new-project fraud-detection 2>/dev/null || oc project fraud-detection
oc apply -f examples/secrets/ -n fraud-detection
```

## Deploy + seed + submit pipeline (one command)

```bash
chmod +x scripts/oneshot.sh
./scripts/oneshot.sh
```

Or GitOps only for platform, then oneshot for seed+submit:

```bash
oc apply -f argocd/application.yaml   # Argo syncs chart/ → fraud-detection
./scripts/oneshot.sh                  # still runs seed + submit (helm is idempotent)
```

## What Helm/Argo owns vs what oneshot triggers

| GitOps (chart / Argo) | oneshot.sh |
|----------------------|------------|
| DSPA, MariaDB, FeatureStore | Seed parquet Job |
| | Upload pipeline + create run Job |

A training **run** is always an explicit trigger (Job or UI) — Argo does not re-train on every sync by design.
