#!/usr/bin/env bash
# Materialize Feast ONLINE inside the FeatureStore online container.
# Does NOT use oc cp (Feast image has no tar → exit 255).
set -euo pipefail
NS="${NS:-fd-gitops}"
FS_NAME="${FS_NAME:-fd-gitops-fs}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

POD=$(oc get pod -n "$NS" -l "feast.dev/name=${FS_NAME}" -o jsonpath='{.items[0].metadata.name}')
echo "Using pod=$POD"

# Stream script into the container (no tar required)
oc exec -i -n "$NS" "$POD" -c online -- tee /tmp/materialize_online.py \
  < "$ROOT/scripts/materialize_online.py" >/dev/null

oc exec -n "$NS" "$POD" -c online -- bash -c '
set -e
export FEAST_S3_PREFIX="${FEAST_S3_PREFIX:-fd-gitops/features}"
export FEAST_REPO="${FEAST_REPO:-/feast-data/fd_gitops/feature_repo}"
python /tmp/materialize_online.py
'
echo "DONE"
