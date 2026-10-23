#!/usr/bin/env bash
# Full synced workflow from a clean or existing fd-gitops project.
# No manual DSPA YAML — Argo applies chart/templates/dspa.yaml from Git.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
chmod +x scripts/*.sh

: "${AWS_S3_ENDPOINT:?}"
: "${PIPELINE_BUCKET:?}"
: "${FEAST_BUCKET:?}"
: "${PG_HOST:?}"
: "${PG_PORT:?}"
: "${PG_USER:?}"
: "${PG_PASSWORD:?}"

echo "======== 1/3 secrets ========"
./scripts/apply_fd_gitops_secrets.sh

echo "======== 2/3 Argo platform ========"
./scripts/configure_argo_site.sh

echo "======== wait platform ========"
NS="${NS:-fd-gitops}"
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

echo "======== 3/3 demo e2e ========"
./scripts/run_demo_e2e.sh
echo "BOOTSTRAP COMPLETE"
