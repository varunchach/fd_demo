#!/usr/bin/env bash
# Site config → Argo Application (platform sync only). Does NOT run seed/train Jobs.
#
# Required env (same as apply_fd_gitops_secrets.sh):
#   AWS_S3_ENDPOINT  PIPELINE_BUCKET  FEAST_BUCKET
#
# Usage:
#   oc apply -f argocd/application.yaml
#   ./scripts/configure_argo_site.sh
#   # wait until Feast Ready + ds-pipeline Service, then:
#   ./scripts/run_demo_e2e.sh
set -euo pipefail

APP_NS="${APP_NS:-openshift-gitops}"
APP_NAME="${APP_NAME:-fd-gitops}"
NS="${NS:-fd-gitops}"

: "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT}"
: "${PIPELINE_BUCKET:?set PIPELINE_BUCKET}"
: "${FEAST_BUCKET:?set FEAST_BUCKET}"

S3_HOST="${AWS_S3_ENDPOINT#https://}"
S3_HOST="${S3_HOST#http://}"
S3_HOST="${S3_HOST%%/*}"

echo "==> Argo site parameters (platform only; hooks stay OFF)"
echo "    pipelines.s3Host=${S3_HOST}"
echo "    pipelines.s3Bucket=${PIPELINE_BUCKET}"
echo "    featureStore.offlineS3Bucket=${FEAST_BUCKET}"

# Replace parameters; force hooks.enabled=false so sync cannot hang on Jobs
oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type json -p "$(cat <<EOF
[
  {
    "op": "add",
    "path": "/spec/source/helm/parameters",
    "value": [
      {"name": "pipelines.s3Host", "value": "${S3_HOST}"},
      {"name": "pipelines.s3Bucket", "value": "${PIPELINE_BUCKET}"},
      {"name": "featureStore.offlineS3Bucket", "value": "${FEAST_BUCKET}"},
      {"name": "hooks.enabled", "value": "false"},
      {"name": "pipelines.deployMariaDB", "value": "true"},
      {"name": "pipelines.deployCustomMariaDB", "value": "false"}
    ]
  }
]
EOF
)"

# Clear old Jobs (never wait — force-delete can hang the script otherwise)
oc delete job fd-gitops-submit-pipeline fd-gitops-seed-offline fd-gitops-materialize-online \
  -n "${NS}" --ignore-not-found --wait=false 2>/dev/null || true

echo "==> refreshing Argo Application"
oc annotate applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" \
  argocd.argoproj.io/refresh=hard --overwrite

echo "==> requesting sync"
oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "{
  \"operation\":{
    \"initiatedBy\":{\"username\":\"${GITOPS_USER:-Varun Raste}\"},
    \"sync\":{\"revision\":\"main\",\"prune\":true}
  }
}"

echo ""
echo "==> DONE (script finished). Platform sync is async in Argo."
echo "    oc get applications.argoproj.io ${APP_NAME} -n ${APP_NS}"
echo "    oc get pods,svc -n ${NS}"
echo "    When FeatureStore Ready + ds-pipeline Service exist:"
echo "    ./scripts/run_demo_e2e.sh"
