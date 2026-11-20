#!/usr/bin/env bash
# Site config → NEW or existing Argo Application (customer only).
# Does NOT touch other namespaces. Platform only — then run_demo_e2e.sh.
#
# Required: AWS_S3_ENDPOINT  PIPELINE_BUCKET  FEAST_BUCKET
# Optional: NS (default fd-gitops), APP_NAME (default NS), FEAST_UI_ENABLED (true/false).
# Existing Helm overrides, including the UI selection, are preserved on reruns.
#
# Safe parallel stack example:
#   export NS=fd-cust APP_NAME=fd-cust
#   ./scripts/configure_argo_site.sh
set -euo pipefail

APP_NS="${APP_NS:-openshift-gitops}"
NS="${NS:-fd-gitops}"
APP_NAME="${APP_NAME:-$NS}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

command -v python3 >/dev/null || { echo "python3 is required to preserve Helm parameters" >&2; exit 1; }
case "${FEAST_UI_ENABLED:-}" in
  ""|true|false) ;;
  *) echo "FEAST_UI_ENABLED must be true or false" >&2; exit 1 ;;
esac

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
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
# Read before applying the bootstrap manifest. Permission/API errors must stop the script.
oc get applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --ignore-not-found \
  -o json > "${TMP_DIR}/application.json"
TMP="${TMP_DIR}/application.yaml"
sed -e "s/__APP_NAME__/${APP_NAME}/g" -e "s/__NS__/${NS}/g" \
  "${ROOT}/argocd/application.yaml.tpl" > "${TMP}"

echo "==> site helm.parameters"
echo "    pipelines.s3Host=${S3_HOST}"
echo "    pipelines.s3Bucket=${PIPELINE_BUCKET}"
echo "    featureStore.offlineS3Bucket=${FEAST_BUCKET}"
echo "    featureStore.offlineS3Prefix=${S3_PREFIX}"

# Merge by parameter name instead of discarding unrelated application overrides.
S3_HOST="$S3_HOST" PIPELINE_BUCKET="$PIPELINE_BUCKET" FEAST_BUCKET="$FEAST_BUCKET" \
S3_PREFIX="$S3_PREFIX" S3_RAW_KEY="$S3_RAW_KEY" FEAST_UI_ENABLED="${FEAST_UI_ENABLED:-}" NS="$NS" \
python3 - "${TMP_DIR}/application.json" > "${TMP_DIR}/merged-parameters.json" <<'PY'
import json
import os
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text().strip()
application = json.loads(raw) if raw else {}
spec = application.get("spec", {})
if application:
    if spec.get("destination", {}).get("namespace") != os.environ["NS"]:
        sys.exit("Existing Application targets a different namespace; select the correct APP_NAME/NS.")
    if spec.get("sources") or not spec.get("source"):
        sys.exit("This setup script requires a single-source Application.")
existing = spec.get("source", {}).get("helm", {}).get("parameters") or []
parameters = {p["name"]: p for p in existing}
updates = {
    "pipelines.s3Host": os.environ["S3_HOST"],
    "pipelines.s3Bucket": os.environ["PIPELINE_BUCKET"],
    "featureStore.offlineS3Bucket": os.environ["FEAST_BUCKET"],
    "featureStore.offlineS3Prefix": os.environ["S3_PREFIX"],
    "hooks.s3RawKey": os.environ["S3_RAW_KEY"],
    "hooks.enabled": "false",
    "pipelines.deployMariaDB": "true",
    "pipelines.deployCustomMariaDB": "false",
    "pipelines.mlflowIntegrationMode": "AUTODETECT",
}
if os.environ["FEAST_UI_ENABLED"]:
    updates["featureStore.uiEnabled"] = os.environ["FEAST_UI_ENABLED"]
for name, value in updates.items():
    parameters[name] = {"name": name, "value": value}
json.dump(list(parameters.values()), sys.stdout)
PY

# Bootstrap only a new Application. Do not reset an existing fork URL, revision,
# value files or destination to the defaults in application.yaml.tpl.
if [[ ! -s "${TMP_DIR}/application.json" ]]; then
  oc apply -f "${TMP}"
fi
oc patch applications.argoproj.io "${APP_NAME}" -n "${APP_NS}" --type merge -p "$(cat <<EOF
{
  "spec": {
    "source": {
      "helm": {
        "parameters": $(cat "${TMP_DIR}/merged-parameters.json")
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
    \"sync\":{\"prune\":true}
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
echo "    Set featureStore.uiEnabled=true on the chosen Argo Application and false on others."
echo "    Keep this selection in Argo/Helm; self-heal restores manually edited CR labels."
echo "    See docs/FEATURE_STORE_UI.md for configuration and read-only verification."
