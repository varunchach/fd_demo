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

# Drop stuck submit hooks so Argo can sync platform (DSPA MariaDB) from Git
oc delete job fd-gitops-submit-pipeline -n fd-gitops --ignore-not-found --force --grace-period=0 2>/dev/null || true

oc annotate applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" \
  argocd.argoproj.io/refresh=hard --overwrite

oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "{
  \"operation\":{
    \"initiatedBy\":{\"username\":\"${USER:-gitops}\"},
    \"sync\":{\"revision\":\"main\",\"prune\":true}
  }
}"

echo "==> done. Argo owns DSPA+Feast from Git (no manual DSPA apply)."
echo "    Registry path: s3://${FEAST_BUCKET}/fd-gitops/registry.db"
echo "    Watch: oc get pods,svc -n fd-gitops -w"
echo "    When ds-pipeline-* Service exists, enable submit:"
echo "      oc patch applications.argoproj.io ${APP_NAME} -n ${APP_NS} --type merge -p '{\"spec\":{\"source\":{\"helm\":{\"parameters\":[{\"name\":\"hooks.submitPipeline\",\"value\":\"true\"}]}}}}'"
echo "      (or re-run with SUBMIT=true ./scripts/configure_argo_site.sh after adding that flag)"
