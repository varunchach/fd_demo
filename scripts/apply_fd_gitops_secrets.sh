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

: "${PG_HOST:?set PG_HOST (Postgres hostname)}"
: "${PG_PORT:?set PG_PORT (e.g. 5432 or 6666 — no default)}"
: "${PG_USER:?set PG_USER}"
: "${PG_PASSWORD:?set PG_PASSWORD}"

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
echo "Next (same env vars) — platform then demo:"
echo "  oc apply -f argocd/application.yaml"
echo "  ./scripts/configure_argo_site.sh   # Argo: DSPA+Feast only (no demo Jobs)"
echo "  # wait: FeatureStore Ready + oc get svc -n fd-gitops | grep ds-pipeline"
echo "  ./scripts/run_demo_e2e.sh         # seed → materialize → submit (outside Argo)"
echo "Secret AWS_S3_BUCKET (${FEAST_BUCKET}) must match FEAST_BUCKET."
