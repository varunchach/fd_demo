#!/usr/bin/env bash
# One-shot: create all 3 secrets for the fd-gitops demo.
#
# S3: same keys/endpoint as an existing secret (default: fraud-mlops/feast-offline-s3),
#     only bucket names change.
# Postgres: YOU supply host/port/user/password (port is NOT assumed — e.g. 6666).
#
# Usage:
#   export PG_HOST=postgres.example.com
#   export PG_PORT=6666                 # REQUIRED — your listener port
#   export PG_USER=feast
#   export PG_PASSWORD='...'
#   export PG_DATABASE=fd_gitops
#   export PIPELINE_BUCKET=fd-gitops-pipeline
#   export FEAST_BUCKET=fd-gitops-features
#   export SRC_NS=fraud-mlops SRC_SECRET=feast-offline-s3
#   ./scripts/apply_fd_gitops_secrets.sh
set -euo pipefail

NS="${NS:-fd-gitops}"
SRC_NS="${SRC_NS:-fraud-mlops}"
SRC_SECRET="${SRC_SECRET:-feast-offline-s3}"
PIPELINE_BUCKET="${PIPELINE_BUCKET:-fd-gitops-pipeline}"
FEAST_BUCKET="${FEAST_BUCKET:-fd-gitops-features}"
PG_DATABASE="${PG_DATABASE:-fd_gitops}"
PG_SCHEMA="${PG_SCHEMA:-public}"
PG_SSLMODE="${PG_SSLMODE:-disable}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# Optional: copy Postgres from an existing Feast online secret (dummy/lab).
#   export PG_SRC_NS=fraud-mlops PG_SRC_SECRET=feast-online-postgres
if [[ -n "${PG_SRC_SECRET:-}" ]]; then
  PG_SRC_NS="${PG_SRC_NS:-$SRC_NS}"
  echo "==> copying Postgres fields from ${PG_SRC_NS}/${PG_SRC_SECRET}"
  PG_YAML=$(oc get secret "$PG_SRC_SECRET" -n "$PG_SRC_NS" -o jsonpath='{.data.feature_store\.yaml}' | base64 -d)
  PG_HOST="${PG_HOST:-$(echo "$PG_YAML" | awk -F': *' '/^host:/{print $2; exit}')}"
  PG_PORT="${PG_PORT:-$(echo "$PG_YAML" | awk -F': *' '/^port:/{print $2; exit}')}"
  PG_USER="${PG_USER:-$(echo "$PG_YAML" | awk -F': *' '/^user:/{print $2; exit}')}"
  PG_PASSWORD="${PG_PASSWORD:-$(echo "$PG_YAML" | awk -F': *' '/^password:/{print $2; exit}')}"
  PG_DATABASE="${PG_DATABASE:-$(echo "$PG_YAML" | awk -F': *' '/^database:/{print $2; exit}')}"
  PG_SCHEMA="${PG_SCHEMA:-$(echo "$PG_YAML" | awk -F': *' '/^db_schema:/{print $2; exit}')}"
  PG_SSLMODE="${PG_SSLMODE:-$(echo "$PG_YAML" | awk -F': *' '/^sslmode:/{print $2; exit}')}"
  PG_SSLMODE="${PG_SSLMODE:-disable}"
fi

: "${PG_HOST:?set PG_HOST (Postgres hostname) or PG_SRC_SECRET}"
: "${PG_PORT:?set PG_PORT (e.g. 5432 or 6666 — no default) or PG_SRC_SECRET}"
: "${PG_USER:?set PG_USER or PG_SRC_SECRET}"
: "${PG_PASSWORD:?set PG_PASSWORD or PG_SRC_SECRET}"

oc new-project "$NS" 2>/dev/null || oc project "$NS"
oc label ns "$NS" opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite

if [[ -z "${AWS_ACCESS_KEY_ID:-}" || -z "${AWS_SECRET_ACCESS_KEY:-}" || -z "${AWS_S3_ENDPOINT:-}" ]]; then
  echo "==> copying S3 keys from ${SRC_NS}/${SRC_SECRET} (buckets will change)"
  AWS_ACCESS_KEY_ID=$(oc get secret "$SRC_SECRET" -n "$SRC_NS" -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)
  AWS_SECRET_ACCESS_KEY=$(oc get secret "$SRC_SECRET" -n "$SRC_NS" -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)
  AWS_S3_ENDPOINT=$(oc get secret "$SRC_SECRET" -n "$SRC_NS" -o jsonpath='{.data.AWS_S3_ENDPOINT}' | base64 -d)
  if oc get secret "$SRC_SECRET" -n "$SRC_NS" -o jsonpath='{.data.AWS_DEFAULT_REGION}' >/dev/null 2>&1; then
    R=$(oc get secret "$SRC_SECRET" -n "$SRC_NS" -o jsonpath='{.data.AWS_DEFAULT_REGION}' | base64 -d || true)
    [[ -n "$R" ]] && REGION="$R"
  fi
fi

S3_HOST="${AWS_S3_ENDPOINT#https://}"
S3_HOST="${S3_HOST#http://}"
S3_HOST="${S3_HOST%%/*}"

echo "==> NS=$NS pipeline_bucket=$PIPELINE_BUCKET feast_bucket=$FEAST_BUCKET"
echo "==> postgres ${PG_HOST}:${PG_PORT}/${PG_DATABASE} user=${PG_USER}"

oc create secret generic fd-gitops-pipeline-s3 -n "$NS" \
  --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  --from-literal=AWS_DEFAULT_REGION="$REGION" \
  --from-literal=AWS_S3_ENDPOINT="$AWS_S3_ENDPOINT" \
  --from-literal=AWS_S3_BUCKET="$PIPELINE_BUCKET" \
  --dry-run=client -o yaml | oc apply -f -

oc create secret generic fd-gitops-feast-s3 -n "$NS" \
  --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
  --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
  --from-literal=AWS_DEFAULT_REGION="$REGION" \
  --from-literal=AWS_ENDPOINT_URL="$AWS_S3_ENDPOINT" \
  --from-literal=AWS_S3_ENDPOINT="$AWS_S3_ENDPOINT" \
  --from-literal=AWS_S3_BUCKET="$FEAST_BUCKET" \
  --from-literal=AWS_S3_FORCE_PATH_STYLE=true \
  --from-literal=AWS_REQUEST_CHECKSUM_CALCULATION=WHEN_REQUIRED \
  --from-literal=AWS_RESPONSE_CHECKSUM_VALIDATION=WHEN_REQUIRED \
  --dry-run=client -o yaml | oc apply -f -

oc create secret generic fd-gitops-feast-pg -n "$NS" \
  --from-literal=feature_store.yaml="$(cat <<EOF
host: ${PG_HOST}
port: ${PG_PORT}
database: ${PG_DATABASE}
db_schema: ${PG_SCHEMA}
user: ${PG_USER}
password: ${PG_PASSWORD}
sslmode: ${PG_SSLMODE}
EOF
)" \
  --dry-run=client -o yaml | oc apply -f -

echo "==> secrets ready:"
oc get secret fd-gitops-pipeline-s3 fd-gitops-feast-s3 fd-gitops-feast-pg -n "$NS"
echo ""
echo "Confirm Postgres port in secret:"
oc get secret fd-gitops-feast-pg -n "$NS" -o jsonpath='{.data.feature_store\.yaml}' | base64 -d | grep -E '^(host|port|database|user):'
echo ""
echo "Next (keep same exports, including NS=${NS}):"
echo "  export APP_NAME=\${APP_NAME:-$NS}"
echo "  ./scripts/configure_argo_site.sh   # creates Argo app → ns ${NS} (do NOT apply application.yaml)"
echo "  # wait: FeatureStore Ready + oc get svc -n ${NS} | grep ds-pipeline"
echo "  NS=${NS} ./scripts/run_demo_e2e.sh"
echo "Note: feast secret bucket is ${FEAST_BUCKET} — keep FEAST_BUCKET set to the same value."
