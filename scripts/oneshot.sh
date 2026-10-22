#!/usr/bin/env bash
# Greenfield CLI path — namespace fd-gitops only (does not touch fraud-detection).
set -euo pipefail
NS="${NS:-fd-gitops}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
FS_NAME="${FS_NAME:-fd-gitops-fs}"

echo "==> project $NS"
oc new-project "$NS" 2>/dev/null || oc project "$NS"
oc label ns "$NS" opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite

echo "==> secrets (fd-gitops-* only)"
oc get secret fd-gitops-pipeline-s3 fd-gitops-feast-s3 fd-gitops-feast-pg -n "$NS"

echo "==> helm (hooks off — we drive seed/materialize/submit below)"
helm upgrade --install fd-gitops ./chart -n "$NS" --set hooks.enabled=false

echo "==> wait FeatureStore"
oc wait --for=jsonpath='{.status.phase}'=Ready "featurestore/${FS_NAME}" -n "$NS" --timeout=600s || true
oc get featurestore,dspa -n "$NS"

echo "==> seed offline parquet"
oc delete job fd-gitops-seed-offline-manual -n "$NS" --ignore-not-found
oc apply -f feature_repo/seed-s3-job.yaml -n "$NS"
oc wait -n "$NS" --for=condition=complete job/fd-gitops-seed-offline-manual --timeout=300s
oc logs -n "$NS" -l job-name=fd-gitops-seed-offline-manual --tail=20

echo "==> materialize ONLINE"
chmod +x scripts/materialize_online.sh
NS="$NS" FS_NAME="$FS_NAME" ./scripts/materialize_online.sh

echo "==> submit pipeline"
oc apply -f scripts/submitter-rbac.yaml -n "$NS"
oc create configmap fd-gitops-pipeline-yaml -n "$NS" \
  --from-file=pipeline.yaml=pipeline/pipeline.yaml --dry-run=client -o yaml | oc apply -f -
oc create configmap fd-gitops-submit-script -n "$NS" \
  --from-file=submit_pipeline_run.py=scripts/submit_pipeline_run.py --dry-run=client -o yaml | oc apply -f -
oc delete job fd-gitops-submit-manual -n "$NS" --ignore-not-found
oc apply -f scripts/submit-pipeline-job.yaml -n "$NS"
oc wait -n "$NS" --for=condition=complete job/fd-gitops-submit-manual --timeout=180s || true
oc logs -n "$NS" -l job-name=fd-gitops-submit-manual --tail=40

oc get workflow -n "$NS"
echo "DONE. GitOps path: docs/GITOPS_DEMO.md"
