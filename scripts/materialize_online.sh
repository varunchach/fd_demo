#!/usr/bin/env bash
# Materialize Feast ONLINE inside the fd-gitops FeatureStore pod.
set -euo pipefail
NS="${NS:-fd-gitops}"
FS_NAME="${FS_NAME:-fd-gitops-fs}"
POD=$(oc get pod -n "$NS" -l "feast.dev/name=${FS_NAME}" -o jsonpath='{.items[0].metadata.name}')
echo "Using pod=$POD"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
oc cp "$ROOT/scripts/materialize_online.py" "$NS/$POD":/tmp/materialize_online.py -c online

oc exec -n "$NS" "$POD" -c online -- bash -c '
set -e
export FEAST_S3_PREFIX="${FEAST_S3_PREFIX:-fd-gitops/features}"
export FEAST_REPO="${FEAST_REPO:-/feast-data/fd_gitops/feature_repo}"
python /tmp/materialize_online.py
'
echo "DONE"
