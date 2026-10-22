#!/usr/bin/env bash
# Inject site-specific Helm parameters into Argo Application from ENV — nothing hardcoded in Git.
#
# Required (same session as apply_fd_gitops_secrets.sh):
#   AWS_S3_ENDPOINT   e.g. https://bls3-rhoat-non-prod.bajajlife.com
#   PIPELINE_BUCKET   e.g. kubeflow-pipelines
#   FEAST_BUCKET      e.g. feature-store
#
# Usage:
#   oc apply -f argocd/application.yaml
#   ./scripts/configure_argo_site.sh
set -euo pipefail

APP_NS="${APP_NS:-openshift-gitops}"
APP_NAME="${APP_NAME:-fd-gitops}"

: "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT}"
: "${PIPELINE_BUCKET:?set PIPELINE_BUCKET}"
: "${FEAST_BUCKET:?set FEAST_BUCKET}"

S3_HOST="${AWS_S3_ENDPOINT#https://}"
S3_HOST="${S3_HOST#http://}"
S3_HOST="${S3_HOST%%/*}"

echo "==> patching Application/${APP_NAME} helm.parameters (replaces any OLD bucket params)"
echo "    pipelines.s3Host=${S3_HOST}"
echo "    pipelines.s3Bucket=${PIPELINE_BUCKET}"
echo "    featureStore.offlineS3Bucket=${FEAST_BUCKET}"
echo "    registry → s3://${FEAST_BUCKET}/fd-gitops/registry.db"

# JSON patch REPLACE the whole parameters array (oc apply alone does NOT clear old params)
oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type json -p "$(cat <<EOF
[
  {
    "op": "add",
    "path": "/spec/source/helm/parameters",
    "value": [
      {"name": "pipelines.s3Host", "value": "${S3_HOST}"},
      {"name": "pipelines.s3Bucket", "value": "${PIPELINE_BUCKET}"},
      {"name": "featureStore.offlineS3Bucket", "value": "${FEAST_BUCKET}"}
    ]
  }
]
EOF
)"

oc annotate applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" \
  argocd.argoproj.io/refresh=hard --overwrite

oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "{
  \"operation\":{
    \"initiatedBy\":{\"username\":\"${USER:-gitops}\"},
    \"sync\":{\"revision\":\"main\"}
  }
}"

echo "==> done. Confirm:"
echo "    oc get featurestore fd-gitops-fs -n fd-gitops -o jsonpath='{.spec.services.registry.local.persistence.file.path}{\"\\n\"}'"
echo "    (expect s3://${FEAST_BUCKET}/fd-gitops/registry.db)"
