#!/usr/bin/env bash
# CLI entrypoint after secrets + values are filled (no Argo required).
# Mirrors Argo PostSync: helm → seed → materialize → submit.
# Usage:  ./scripts/oneshot.sh
set -euo pipefail
NS="${NS:-fraud-detection}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> project $NS"
oc new-project "$NS" 2>/dev/null || oc project "$NS"
oc label ns "$NS" opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite

echo "==> secrets (must already contain real values)"
oc get secret pipeline-artifacts feast-offline-s3 feast-online-postgres -n "$NS"

echo "==> helm (DSPA + FeatureStore; hooks.enabled may create PostSync Jobs if used by Argo)"
# Local helm install does NOT run Argo hooks — we drive seed/materialize/submit below.
helm upgrade --install fraud-detection ./chart -n "$NS" \
  --set hooks.enabled=false

echo "==> wait FeatureStore + DSPA"
oc wait --for=jsonpath='{.status.phase}'=Ready featurestore/fraud-feature-store -n "$NS" --timeout=600s || true
oc get featurestore,dspa -n "$NS"

echo "==> seed offline parquet"
oc delete job seed-features-to-s3 -n "$NS" --ignore-not-found
oc apply -f feature_repo/seed-s3-job.yaml -n "$NS"
oc wait -n "$NS" --for=condition=complete job/seed-features-to-s3 --timeout=300s
oc logs -n "$NS" -l job-name=seed-features-to-s3 --tail=20

echo "==> materialize ONLINE store (Feast pod)"
chmod +x scripts/materialize_online.sh
NS="$NS" ./scripts/materialize_online.sh

echo "==> submit pipeline (CLI)"
oc apply -f scripts/submitter-rbac.yaml -n "$NS"
oc create configmap fraud-detection-pipeline-yaml -n "$NS" \
  --from-file=pipeline.yaml=pipeline/pipeline.yaml --dry-run=client -o yaml | oc apply -f -
oc create configmap feast-submit-script -n "$NS" \
  --from-file=submit_pipeline_run.py=scripts/submit_pipeline_run.py --dry-run=client -o yaml | oc apply -f -
oc delete job submit-fraud-pipeline -n "$NS" --ignore-not-found
oc apply -f scripts/submit-fraud-pipeline-job.yaml -n "$NS"
oc wait -n "$NS" --for=condition=complete job/submit-fraud-pipeline --timeout=180s || true
oc logs -n "$NS" -l job-name=submit-fraud-pipeline --tail=40

echo "==> pipeline workflows"
oc get workflow -n "$NS"
echo "DONE. Watch: oc get workflow -n $NS -w"
echo "GitOps path: docs/GITOPS_DEMO.md"
