#!/usr/bin/env bash
# SINGLE COMMAND: secrets → Argo (DSPA+Feast from Git) → e2e → UI checks
# No manual DSPA YAML. Pipeline submit is included (not a dashboard click).
#
# Required: PIPELINE_BUCKET FEAST_BUCKET
#   AWS: AWS_S3_ENDPOINT (+ keys) OR copy via SRC_NS/SRC_SECRET
#   PG:  PG_HOST PG_PORT PG_USER PG_PASSWORD (or PG_SRC_SECRET from existing Feast secret)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x scripts/*.sh

: "${PIPELINE_BUCKET:?set PIPELINE_BUCKET}"
: "${FEAST_BUCKET:?set FEAST_BUCKET}"
if [[ -z "${AWS_S3_ENDPOINT:-}" && -z "${SRC_SECRET:-}" ]]; then
  : "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT or SRC_SECRET}"
fi
if [[ -z "${PG_HOST:-}" && -z "${PG_SRC_SECRET:-}" ]]; then
  : "${PG_HOST:?set PG_* or PG_SRC_SECRET}"
fi

NS="${NS:-fd-gitops}"

echo "======== 1/4 secrets ========"
./scripts/apply_fd_gitops_secrets.sh

if [[ -z "${AWS_S3_ENDPOINT:-}" ]]; then
  AWS_S3_ENDPOINT=$(oc get secret fd-gitops-feast-s3 -n "$NS" -o jsonpath='{.data.AWS_S3_ENDPOINT}' | base64 -d)
  export AWS_S3_ENDPOINT
fi

echo "======== 2/4 Argo platform ========"
./scripts/configure_argo_site.sh

echo "======== 3/4 wait Ready ========"
for i in $(seq 1 90); do
  FS=$(oc get featurestore fd-gitops-fs -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  SVC=$(oc get svc ds-pipeline-fd-gitops-dspa -n "$NS" -o name 2>/dev/null || true)
  echo "  [$i] FeatureStore=${FS:-none} pipelineSvc=${SVC:-none}"
  if [[ "$FS" == "Ready" && -n "$SVC" ]]; then
    break
  fi
  sleep 10
done
oc get featurestore fd-gitops-fs -n "$NS"
oc get svc ds-pipeline-fd-gitops-dspa -n "$NS" >/dev/null

echo "======== 4/4 demo e2e ========"
./scripts/run_demo_e2e.sh
./scripts/verify_featurestore_ui.sh
echo "BOOTSTRAP COMPLETE"
echo "See Argo app: oc get applications.argoproj.io -n openshift-gitops"
echo "Docs: docs/WHERE_TO_LOOK.md"
