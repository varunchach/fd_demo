#!/usr/bin/env bash
# Demo data path — OUTSIDE Argo. Works for any NS (fd-cust, fd-gitops, …).
# Prereq: FeatureStore Ready + ds-pipeline Service
set -euo pipefail

NS="${NS:-fd-gitops}"
FS_NAME="${FS_NAME:-fd-gitops-fs}"
DSPA_NAME="${DSPA_NAME:-fd-gitops-dspa}"
S3_PREFIX="${S3_PREFIX:-${NS}/features}"
S3_RAW_KEY="${S3_RAW_KEY:-${NS}/raw/transactions.csv}"
MODEL_S3_KEY="${MODEL_S3_KEY:-${NS}/models/fraud-model.pkl}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> stack NS=${NS} FS=${FS_NAME} DSPA=${DSPA_NAME} prefix=${S3_PREFIX}"

echo "==> wait FeatureStore Ready"
PHASE=""
for i in $(seq 1 60); do
  PHASE=$(oc get featurestore "${FS_NAME}" -n "${NS}" -o jsonpath='{.status.phase}' 2>/dev/null || true)
  if [[ "${PHASE}" == "Ready" ]]; then
    echo "    FeatureStore Ready"
    break
  fi
  echo "    phase=${PHASE:-none} (${i}/60)"
  sleep 10
done
[[ "${PHASE:-}" == "Ready" ]] || { echo "FeatureStore not Ready"; exit 1; }

REG=$(oc get featurestore "${FS_NAME}" -n "${NS}" \
  -o jsonpath='{.spec.services.registry.local.persistence.file.path}')
BUCKET=$(oc get secret fd-gitops-feast-s3 -n "${NS}" -o jsonpath='{.data.AWS_S3_BUCKET}' | base64 -d)
echo "    registry=${REG}"
echo "    secret bucket=${BUCKET}"
if [[ "${REG}" == s3://* ]]; then
  echo "${REG}" | grep -q "s3://${BUCKET}/" || {
    echo "ERROR: registry path bucket != secret AWS_S3_BUCKET — re-run configure_argo_site.sh"
    exit 1
  }
fi

echo "==> wait DSPA API Service"
SVC="ds-pipeline-${DSPA_NAME}"
for i in $(seq 1 60); do
  if oc get svc "${SVC}" -n "${NS}" >/dev/null 2>&1; then
    echo "    Service ${SVC} OK"
    break
  fi
  echo "    waiting for ${SVC} (${i}/60)"
  sleep 10
done
oc get svc "${SVC}" -n "${NS}" >/dev/null

echo "==> seed offline parquet"
oc delete job fd-gitops-seed-offline-manual -n "${NS}" --ignore-not-found
sed -e "s|PLACEHOLDER_S3_PREFIX|${S3_PREFIX}|g" \
  "${ROOT}/feature_repo/seed-s3-job.yaml" | oc apply -n "${NS}" -f -
oc wait -n "${NS}" --for=condition=complete job/fd-gitops-seed-offline-manual --timeout=300s
oc logs -n "${NS}" -l job-name=fd-gitops-seed-offline-manual --tail=20

echo "==> materialize online"
chmod +x scripts/materialize_online.sh
NS="${NS}" FS_NAME="${FS_NAME}" FEAST_S3_PREFIX="${S3_PREFIX}" ./scripts/materialize_online.sh

echo "==> submitter RBAC + pipeline job"
sed -e "s|PLACEHOLDER_NS|${NS}|g" scripts/submitter-rbac.yaml | oc apply -n "${NS}" -f -

oc create configmap fd-gitops-pipeline-yaml -n "${NS}" \
  --from-file=pipeline.yaml=pipeline/pipeline.yaml --dry-run=client -o yaml | oc apply -n "${NS}" -f -
oc create configmap fd-gitops-submit-script -n "${NS}" \
  --from-file=submit_pipeline_run.py=scripts/submit_pipeline_run.py --dry-run=client -o yaml | oc apply -n "${NS}" -f -

oc delete job fd-gitops-submit-manual -n "${NS}" --ignore-not-found
cat <<EOF | oc apply -n "${NS}" -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: fd-gitops-submit-manual
spec:
  ttlSecondsAfterFinished: 600
  backoffLimit: 1
  template:
    spec:
      serviceAccountName: fd-gitops-submitter
      restartPolicy: Never
      containers:
        - name: submit
          image: image-registry.openshift-image-registry.svc:5000/redhat-ods-applications/s2i-generic-data-science-notebook:3.5
          envFrom:
            - secretRef:
                name: fd-gitops-pipeline-s3
          env:
            - name: HOME
              value: /tmp
            - name: NAMESPACE
              value: "${NS}"
            - name: DSPA_API
              value: "https://ds-pipeline-${DSPA_NAME}.${NS}.svc.cluster.local:8443"
            - name: DSPA_NAME
              value: "${DSPA_NAME}"
            - name: FEAST_URL
              value: "https://feast-${FS_NAME}-online.${NS}.svc.cluster.local:443"
            - name: FEAST_NAME
              value: "${FS_NAME}"
            - name: MLFLOW_TRACKING_URI
              value: https://mlflow.redhat-ods-applications.svc.cluster.local:8443/mlflow
            - name: PIPELINE_FILE
              value: /pipeline/pipeline.yaml
            - name: PIPELINE_DISPLAY_NAME
              value: fd-gitops-pipeline
            - name: EXPERIMENT_NAME
              value: "${NS}-training"
            - name: RUN_NAME
              value: "${NS}-e2e"
            - name: UPLOAD_NEW_VERSION
              value: "true"
            - name: PIPELINE_SA
              value: "pipeline-runner-${DSPA_NAME}"
            - name: S3_KEY
              value: "${S3_RAW_KEY}"
            - name: MODEL_S3_KEY
              value: "${MODEL_S3_KEY}"
          command: ["python", "/scripts/submit_pipeline_run.py"]
          volumeMounts:
            - name: scripts
              mountPath: /scripts
            - name: pipeline
              mountPath: /pipeline
      volumes:
        - name: scripts
          configMap:
            name: fd-gitops-submit-script
        - name: pipeline
          configMap:
            name: fd-gitops-pipeline-yaml
EOF

oc wait -n "${NS}" --for=condition=complete job/fd-gitops-submit-manual --timeout=180s || true
oc logs -n "${NS}" -l job-name=fd-gitops-submit-manual --tail=40

echo "==> workflows"
oc get workflow -n "${NS}" 2>/dev/null || oc get workflows.argoproj.io -n "${NS}" 2>/dev/null || true
echo "DONE. Watch: oc get workflow -n ${NS} -w"
