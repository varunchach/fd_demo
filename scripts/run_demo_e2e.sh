#!/usr/bin/env bash
# Demo data path — runs OUTSIDE Argo so sync stays healthy.
# Prereq: platform Ready (Feast + ds-pipeline Service) via configure_argo_site.sh
set -euo pipefail

NS="${NS:-fd-gitops}"
FS_NAME="${FS_NAME:-fd-gitops-fs}"
DSPA_NAME="${DSPA_NAME:-fd-gitops-dspa}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> wait FeatureStore Ready"
for i in $(seq 1 60); do
  PHASE=$(oc get featurestore "${FS_NAME}" -n "${NS}" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  if [[ "${PHASE}" == "Ready" ]]; then
    echo "    FeatureStore Ready"
    break
  fi
  echo "    phase=${PHASE:-none} (${i}/60)"
  sleep 10
done
[[ "${PHASE:-}" == "Ready" ]] || { echo "FeatureStore not Ready"; exit 1; }

REG=$(oc get featurestore "${FS_NAME}" -n "${NS}" \
  -o jsonpath='{.spec.services.registry.local.persistence.file.path}')
echo "    registry=${REG}"
BUCKET=$(oc get secret fd-gitops-feast-s3 -n "${NS}" -o jsonpath='{.data.AWS_S3_BUCKET}' | base64 -d)
echo "    secret bucket=${BUCKET}"
# Customer: registry must be s3://$FEAST_BUCKET/...
# Lab: local path /feast-data/registry.db is OK
if [[ "${REG}" == s3://* ]]; then
  echo "${REG}" | grep -q "s3://${BUCKET}/" || {
    echo "ERROR: registry path bucket != secret AWS_S3_BUCKET — re-run configure_argo_site.sh"
    exit 1
  }
else
  echo "    lab local registry OK"
fi

echo "==> wait DSPA API Service"
SVC="ds-pipeline-${DSPA_NAME}"
for i in $(seq 1 60); do
  if oc get svc "${SVC}" -n "${NS}" >/dev/null 2>&1; then
    echo "    Service ${SVC} OK"
    break
  fi
  echo "    waiting for ${SVC} (${i}/60)"
  sleep 10
done
oc get svc "${SVC}" -n "${NS}" >/dev/null

echo "==> seed offline parquet"
oc delete job fd-gitops-seed-offline-manual -n "${NS}" --ignore-not-found
oc apply -f feature_repo/seed-s3-job.yaml -n "${NS}"
oc wait -n "${NS}" --for=condition=complete job/fd-gitops-seed-offline-manual --timeout=300s
oc logs -n "${NS}" -l job-name=fd-gitops-seed-offline-manual --tail=20

echo "==> materialize online"
chmod +x scripts/materialize_online.sh
NS="${NS}" FS_NAME="${FS_NAME}" ./scripts/materialize_online.sh

echo "==> submit pipeline"
oc apply -f scripts/submitter-rbac.yaml -n "${NS}"
oc create configmap fd-gitops-pipeline-yaml -n "${NS}" \
  --from-file=pipeline.yaml=pipeline/pipeline.yaml --dry-run=client -o yaml | oc apply -f -
oc create configmap fd-gitops-submit-script -n "${NS}" \
  --from-file=submit_pipeline_run.py=scripts/submit_pipeline_run.py --dry-run=client -o yaml | oc apply -f -
oc delete job fd-gitops-submit-manual -n "${NS}" --ignore-not-found
oc apply -f scripts/submit-pipeline-job.yaml -n "${NS}"
oc wait -n "${NS}" --for=condition=complete job/fd-gitops-submit-manual --timeout=180s || true
oc logs -n "${NS}" -l job-name=fd-gitops-submit-manual --tail=40

echo "==> workflows"
oc get workflow -n "${NS}"
echo "DONE. Watch: oc get workflow -n ${NS} -w"
