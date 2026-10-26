#!/usr/bin/env bash
# Site config → NEW or existing Argo Application (customer only).
# Does NOT touch other namespaces. Platform only — then run_demo_e2e.sh.
#
# Required: AWS_S3_ENDPOINT  PIPELINE_BUCKET  FEAST_BUCKET
# Optional: NS  APP_NAME  (default both fd-gitops)
#
# Safe parallel stack example:
#   export NS=fd-cust APP_NAME=fd-cust
#   ./scripts/configure_argo_site.sh
set -euo pipefail

APP_NS="${APP_NS:-openshift-gitops}"
APP_NAME="${APP_NAME:-fd-gitops}"
NS="${NS:-fd-gitops}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

: "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT}"
: "${PIPELINE_BUCKET:?set PIPELINE_BUCKET}"
: "${FEAST_BUCKET:?set FEAST_BUCKET}"

S3_HOST="${AWS_S3_ENDPOINT#https://}"
S3_HOST="${S3_HOST#http://}"
S3_HOST="${S3_HOST%%/*}"
# Isolate S3 object paths per namespace when sharing buckets
S3_PREFIX="${S3_PREFIX:-${NS}/features}"
S3_RAW_KEY="${S3_RAW_KEY:-${NS}/raw/transactions.csv}"

echo "==> Argo Application ${APP_NAME} → namespace ${NS}"
TMP="$(mktemp)"
sed -e "s/__APP_NAME__/${APP_NAME}/g" -e "s/__NS__/${NS}/g" \
  "${ROOT}/argocd/application.yaml.tpl" > "${TMP}"
oc apply -f "${TMP}"
rm -f "${TMP}"

echo "==> site helm.parameters"
echo "    pipelines.s3Host=${S3_HOST}"
echo "    pipelines.s3Bucket=${PIPELINE_BUCKET}"
echo "    featureStore.offlineS3Bucket=${FEAST_BUCKET}"
echo "    featureStore.offlineS3Prefix=${S3_PREFIX}"

# replace parameters array (add fails if already present)
oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "$(cat <<EOF
{
  "spec": {
    "source": {
      "helm": {
        "parameters": [
          {"name": "pipelines.s3Host", "value": "${S3_HOST}"},
          {"name": "pipelines.s3Bucket", "value": "${PIPELINE_BUCKET}"},
          {"name": "featureStore.offlineS3Bucket", "value": "${FEAST_BUCKET}"},
          {"name": "featureStore.offlineS3Prefix", "value": "${S3_PREFIX}"},
          {"name": "hooks.s3RawKey", "value": "${S3_RAW_KEY}"},
          {"name": "hooks.enabled", "value": "false"},
          {"name": "pipelines.deployMariaDB", "value": "true"},
          {"name": "pipelines.deployCustomMariaDB", "value": "false"},
          {"name": "pipelines.mlflowIntegrationMode", "value": "AUTODETECT"}
        ]
      }
    },
    "syncPolicy": {
      "automated": {"prune": true, "selfHeal": true},
      "syncOptions": [
        "CreateNamespace=true",
        "RespectIgnoreDifferences=true",
        "ApplyOutOfSyncOnly=true"
      ],
      "retry": {"limit": 5, "backoff": {"duration": "30s", "factor": 2, "maxDuration": "5m"}}
    }
  }
}
EOF
)"

oc annotate applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" \
  argocd.argoproj.io/refresh=hard --overwrite

oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "{
  \"operation\":{
    \"initiatedBy\":{\"username\":\"${GITOPS_USER:-customer}\"},
    \"sync\":{\"revision\":\"main\",\"prune\":true}
  }
}"

echo ""
echo "==> DONE. Left other namespaces alone."
echo "    Wait: oc get application ${APP_NAME} -n ${APP_NS}"
echo "          oc get featurestore,dspa -n ${NS}"
echo "          oc get svc -n ${NS} | grep ds-pipeline"
echo "    Then: NS=${NS} DSPA_NAME=fd-gitops-dspa FS_NAME=fd-gitops-fs ./scripts/run_demo_e2e.sh"
echo ""
echo "    Feature Store UI: only ONE cluster FeatureStore may have label feature-store-ui=enabled."
echo "    If an older stack still has it: oc label featurestore fd-gitops-fs -n <old-ns> feature-store-ui-"
