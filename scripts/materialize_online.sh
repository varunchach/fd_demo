#!/usr/bin/env bash
# Materialize Feast ONLINE store from S3 parquet (inside Feast online container).
set -euo pipefail
NS="${NS:-fraud-detection}"
POD=$(oc get pod -n "$NS" -l feast.dev/name=fraud-feature-store -o jsonpath='{.items[0].metadata.name}')
echo "Using pod=$POD"

# Copy script into pod
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
oc cp "$ROOT/scripts/materialize_online.py" "$NS/$POD":/tmp/materialize_online.py -c online

oc exec -n "$NS" "$POD" -c online -- bash -c '
set -e
export FEAST_S3_PREFIX="${FEAST_S3_PREFIX:-fraud-detection/features}"
# AWS_* come from envFrom feast-offline-s3 on the online container
python /tmp/materialize_online.py
'

echo "DONE — verify online features, then resubmit DSPA pipeline"
