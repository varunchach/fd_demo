#!/usr/bin/env bash
# Verify Feast offline S3 + registry + UI credentials are wired correctly.
set -euo pipefail
NS="${NS:-fd-gitops}"
FS="${FS_NAME:-fd-gitops-fs}"
S3_SECRET="${S3_SECRET:-fd-gitops-feast-s3}"
PG_SECRET="${PG_SECRET:-fd-gitops-feast-pg}"

echo "==> namespace $NS featurestore $FS"
ok=0
fail=0
check() {
  local name="$1" cond="$2"
  if eval "$cond"; then
    echo "  OK  $name"
    ok=$((ok + 1))
  else
    echo "  FAIL $name"
    fail=$((fail + 1))
  fi
}

check "secret $S3_SECRET exists" "oc get secret $S3_SECRET -n $NS >/dev/null 2>&1"
check "secret has AWS_ACCESS_KEY_ID" "oc get secret $S3_SECRET -n $NS -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | grep -q ."
check "secret has AWS_SECRET_ACCESS_KEY" "oc get secret $S3_SECRET -n $NS -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | grep -q ."
check "secret has AWS_ENDPOINT_URL (boto3/Feast)" "oc get secret $S3_SECRET -n $NS -o jsonpath='{.data.AWS_ENDPOINT_URL}' | grep -q ."
check "secret has AWS_S3_BUCKET" "oc get secret $S3_SECRET -n $NS -o jsonpath='{.data.AWS_S3_BUCKET}' | grep -q ."
check "secret has checksum WHEN_REQUIRED" "oc get secret $S3_SECRET -n $NS -o jsonpath='{.data.AWS_REQUEST_CHECKSUM_CALCULATION}' | base64 -d 2>/dev/null | grep -q WHEN_REQUIRED"

BUCKET=$(oc get secret "$S3_SECRET" -n "$NS" -o jsonpath='{.data.AWS_S3_BUCKET}' | base64 -d)
echo "  INFO feast S3 bucket=$BUCKET"

if oc get featurestore "$FS" -n "$NS" >/dev/null 2>&1; then
  REG_PATH=$(oc get featurestore "$FS" -n "$NS" -o jsonpath='{.spec.services.registry.local.persistence.file.path}')
  echo "  INFO registryS3Path=$REG_PATH"
  check "registry path uses feast bucket" "echo \"$REG_PATH\" | grep -q \"s3://${BUCKET}/\""
  check "online envFrom → $S3_SECRET" \
    "oc get featurestore $FS -n $NS -o jsonpath='{.spec.services.onlineStore.server.envFrom[*].secretRef.name}' | grep -q $S3_SECRET"
  check "registry envFrom → $S3_SECRET" \
    "oc get featurestore $FS -n $NS -o jsonpath='{.spec.services.registry.local.server.envFrom[*].secretRef.name}' | grep -q $S3_SECRET"
  check "ui envFrom → $S3_SECRET" \
    "oc get featurestore $FS -n $NS -o jsonpath='{.spec.services.ui.envFrom[*].secretRef.name}' | grep -q $S3_SECRET"
  PHASE=$(oc get featurestore "$FS" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  echo "  INFO FeatureStore phase=${PHASE:-unknown}"
  check "FeatureStore Ready" "[[ \"$PHASE\" == \"Ready\" ]]"
else
  echo "  SKIP FeatureStore not created yet (apply Argo / helm first)"
fi

check "postgres secret $PG_SECRET exists" "oc get secret $PG_SECRET -n $NS >/dev/null 2>&1"
if oc get secret "$PG_SECRET" -n "$NS" >/dev/null 2>&1; then
  echo "  INFO postgres connection fields:"
  oc get secret "$PG_SECRET" -n "$NS" -o jsonpath='{.data.feature_store\.yaml}' | base64 -d | grep -E '^(host|port|database|user|sslmode):' | sed 's/^/       /'
  check "postgres secret has port field" \
    "oc get secret $PG_SECRET -n $NS -o jsonpath='{.data.feature_store\.yaml}' | base64 -d | grep -qE '^port:[[:space:]]*[0-9]+'"
  check "postgres secret is FLAT (no online_store wrapper)" \
    "! oc get secret $PG_SECRET -n $NS -o jsonpath='{.data.feature_store\.yaml}' | base64 -d | grep -q online_store"
fi

echo ""
echo "Result: $ok ok, $fail fail"
[[ "$fail" -eq 0 ]]
