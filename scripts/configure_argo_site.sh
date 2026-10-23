#!/usr/bin/env bash
# Site config → Argo Application. Restores autosync from Git (undoes any manual freeze).
# Platform only — does NOT run seed/train (see run_demo_e2e.sh).
#
# Required: AWS_S3_ENDPOINT  PIPELINE_BUCKET  FEAST_BUCKET
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

echo "==> ensure Argo Application + RBAC from Git (re-enables automated sync)"
oc apply -f "${ROOT}/argocd/application.yaml"

echo "==> site helm.parameters (DSPA managed MariaDB in Git; hooks OFF)"
echo "    pipelines.s3Host=${S3_HOST}"
echo "    pipelines.s3Bucket=${PIPELINE_BUCKET}"
echo "    featureStore.offlineS3Bucket=${FEAST_BUCKET}"

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
      {"name": "pipelines.deployCustomMariaDB", "value": "false"},
      {"name": "pipelines.mlflowIntegrationMode", "value": "AUTODETECT"}
    ]
  }
]
EOF
)"

# Ensure syncPolicy is automated again (clears syncPolicy:null freezes)
oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p '{
  "spec":{
    "syncPolicy":{
      "automated":{"prune":true,"selfHeal":true},
      "syncOptions":[
        "CreateNamespace=true",
        "RespectIgnoreDifferences=true",
        "ApplyOutOfSyncOnly=true"
      ],
      "retry":{"limit":5,"backoff":{"duration":"30s","factor":2,"maxDuration":"5m"}}
    }
  }
}'

oc delete job fd-gitops-submit-pipeline fd-gitops-seed-offline fd-gitops-materialize-online \
  -n "${NS}" --ignore-not-found --wait=false 2>/dev/null || true

oc annotate applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" \
  argocd.argoproj.io/refresh=hard --overwrite

oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "{
  \"operation\":{
    \"initiatedBy\":{\"username\":\"${GITOPS_USER:-Varun Raste}\"},
    \"sync\":{\"revision\":\"main\",\"prune\":true}
  }
}"

echo ""
echo "==> DONE. Argo owns DSPA (Replace=true + mariaDB.deploy) + Feast from Git."
echo "    Wait: oc get featurestore,dspa -n ${NS}"
echo "          oc get svc -n ${NS} | grep ds-pipeline"
echo "    Then: ./scripts/run_demo_e2e.sh"
