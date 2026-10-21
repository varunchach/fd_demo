#!/usr/bin/env bash
# Create namespace + S3 Data Connection secrets for the fraud-mlops demo.
# Usage:
#   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_S3_ENDPOINT=... AWS_S3_BUCKET=...
#   ./scripts/setup-prereqs.sh
#
# Or copy an existing MinIO data-connection secret from another project:
#   ./scripts/setup-prereqs.sh --from-secret minio-data-connection --from-ns credit-decisioning
set -euo pipefail

NS="${NS:-fraud-mlops}"
MY_STORAGE="${MY_STORAGE_SECRET:-my-storage}"
PIPE_STORAGE="${PIPELINE_ARTIFACTS_SECRET:-pipeline-artifacts}"

FROM_SECRET=""
FROM_NS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-secret) FROM_SECRET="$2"; shift 2 ;;
    --from-ns) FROM_NS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

oc get ns "$NS" >/dev/null 2>&1 || oc create ns "$NS"
oc label ns "$NS" opendatahub.io/dashboard=true --overwrite

if [[ -n "$FROM_SECRET" && -n "$FROM_NS" ]]; then
  echo "Copying secret $FROM_NS/$FROM_SECRET → $NS/$MY_STORAGE and $PIPE_STORAGE"
  oc get secret "$FROM_SECRET" -n "$FROM_NS" -o json \
    | python -c "
import json,sys
s=json.load(sys.stdin)
s['metadata']={'name':'$MY_STORAGE','namespace':'$NS'}
s.pop('resourceVersion',None); s.pop('uid',None); s.pop('creationTimestamp',None)
print(json.dumps(s))
" | oc apply -f -
  oc get secret "$FROM_SECRET" -n "$FROM_NS" -o json \
    | python -c "
import json,sys
s=json.load(sys.stdin)
s['metadata']={'name':'$PIPE_STORAGE','namespace':'$NS'}
s.pop('resourceVersion',None); s.pop('uid',None); s.pop('creationTimestamp',None)
# Ensure DSPA bucket name matches chart values-demo (pipeline-artifacts)
data=s.get('data',{})
import base64
data['AWS_S3_BUCKET']=base64.b64encode(b'pipeline-artifacts').decode()
s['data']=data
print(json.dumps(s))
" | oc apply -f -
else
  : "${AWS_ACCESS_KEY_ID:?set AWS_ACCESS_KEY_ID}"
  : "${AWS_SECRET_ACCESS_KEY:?set AWS_SECRET_ACCESS_KEY}"
  : "${AWS_S3_ENDPOINT:?set AWS_S3_ENDPOINT}"
  : "${AWS_S3_BUCKET:?set AWS_S3_BUCKET}"
  REGION="${AWS_DEFAULT_REGION:-us-east-1}"
  for NAME in "$MY_STORAGE" "$PIPE_STORAGE"; do
    oc create secret generic "$NAME" -n "$NS" \
      --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
      --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
      --from-literal=AWS_S3_ENDPOINT="$AWS_S3_ENDPOINT" \
      --from-literal=AWS_S3_BUCKET="$AWS_S3_BUCKET" \
      --from-literal=AWS_DEFAULT_REGION="$REGION" \
      --dry-run=client -o yaml | oc apply -f -
  done
fi

echo "Prereqs ready in namespace $NS"
oc get secrets -n "$NS" | grep -E "$MY_STORAGE|$PIPE_STORAGE" || true
