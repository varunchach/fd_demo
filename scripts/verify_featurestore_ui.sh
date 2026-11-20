#!/usr/bin/env bash
# Read-only checks for RHOAI 3.5 dashboard discovery of this chart's noAuth registry.
# Run with the same OpenShift account used in the dashboard where possible.
set -euo pipefail

NS="${NS:-fd-gitops}"
FS_NAME="${FS_NAME:-fd-gitops-fs}"
DASHBOARD_NS="${DASHBOARD_NS:-redhat-ods-applications}"
DASHBOARD_DEPLOYMENT="${DASHBOARD_DEPLOYMENT:-rhods-dashboard}"

echo "==> namespace labels"
for label in dashboard feast; do
  VALUE=$(oc get namespace "$NS" -o "jsonpath={.metadata.labels.opendatahub\\.io/${label}}")
  [[ "$VALUE" == "true" ]] || {
    echo "FAIL: missing opendatahub.io/${label}=true on ${NS}" >&2; exit 1;
  }
done

echo "==> FeatureStore discovery settings"
LABEL=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.metadata.labels.feature-store-ui}')
PROJECT=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.spec.feastProject}')
READY=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.status.conditions[?(@.type=="Registry")].status}')
REST_ENABLED=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.spec.services.registry.local.server.restAPI}')
REGISTRY_HOST=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.status.serviceHostnames.registryRest}')
TLS_DISABLED=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.spec.services.registry.local.server.tls.disable}')
NO_AUTH=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.spec.authz.noAuth}')
[[ "$LABEL" == "enabled" ]] || { echo "FAIL: enable featureStore.uiEnabled in this Argo Application" >&2; exit 1; }
[[ "$READY" == "True" ]] || { echo "FAIL: Registry condition is ${READY:-missing}" >&2; exit 1; }
[[ "$REST_ENABLED" == "true" && -n "$REGISTRY_HOST" && -n "$PROJECT" ]] || {
  echo "FAIL: REST API configuration, service hostname, or Feast project is missing" >&2; exit 1;
}
echo "    ${NS}/${FS_NAME}; Feast project=${PROJECT}; registry=${REGISTRY_HOST}"

echo "==> UI-enabled instances (requires cluster-wide list permission)"
ENABLED=$(oc get featurestore -A -l feature-store-ui=enabled \
  -o jsonpath='{range .items[*]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}')
printf '%s\n' "$ENABLED"
COUNT=$(printf '%s\n' "$ENABLED" | awk 'NF {n++} END {print n+0}')
[[ "$COUNT" == "1" ]] || {
  echo "FAIL: expected one UI-enabled instance, found ${COUNT}. Set featureStore.uiEnabled=false on other Argo Applications." >&2
  exit 1
}

echo "==> project discovery from the dashboard pod"
[[ "$NO_AUTH" == "true" ]] || {
  echo "INCOMPLETE: this probe targets the chart's noAuth registry; an authenticated registry needs an authenticated request." >&2
  exit 2
}
if [[ -z "${DASHBOARD_CONTAINER:-}" ]]; then
  CONTAINERS=$(oc get deployment "$DASHBOARD_DEPLOYMENT" -n "$DASHBOARD_NS" \
    -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\n"}{end}')
  while IFS= read -r container; do
    case "$container" in
      rhods-dashboard|odh-dashboard) DASHBOARD_CONTAINER="$container"; break ;;
    esac
  done <<< "$CONTAINERS"
fi
[[ -n "${DASHBOARD_CONTAINER:-}" ]] || {
  echo "INCOMPLETE: set DASHBOARD_CONTAINER to the dashboard's Node.js container" >&2; exit 2;
}
PROTOCOL=https
[[ "$TLS_DISABLED" == "true" ]] && PROTOCOL=http
oc exec -i -n "$DASHBOARD_NS" "deployment/${DASHBOARD_DEPLOYMENT}" -c "$DASHBOARD_CONTAINER" -- \
  node - "${PROTOCOL}://${REGISTRY_HOST}/api/v1/projects" "$PROJECT" <<'JS'
const url = new URL(process.argv[2]);
const project = process.argv[3];
const client = require(url.protocol === 'https:' ? 'https' : 'http');
// Match the dashboard's registry proxy for this connectivity diagnostic only.
const request = client.get(url, {rejectUnauthorized: false, timeout: 10000}, response => {
  let body = '';
  response.setEncoding('utf8');
  response.on('data', chunk => { body += chunk; });
  response.on('error', error => { console.error('FAIL:', error.message); process.exitCode = 1; });
  response.on('end', () => {
    try {
      if (response.statusCode !== 200) throw new Error(`registry returned HTTP ${response.statusCode}`);
      const data = JSON.parse(body);
      const names = (data.projects || []).map(p => p.spec?.name || p.name);
      if (!names.includes(project)) {
        throw new Error(`expected project ${project}; registry returned ${JSON.stringify(names)}`);
      }
      console.log(`PASS: dashboard can reach the registry and discover ${project}`);
    } catch (error) {
      console.error('FAIL:', error.message);
      process.exitCode = 1;
    }
  });
});
request.on('timeout', () => request.destroy(new Error('dashboard-to-registry request timed out')));
request.on('error', error => { console.error('FAIL:', error.message); process.exitCode = 1; });
JS

echo "Discovery checks passed. Open Develop & train → Feature Store and look for ${PROJECT}."
echo "Dashboard user access must also allow listing this project and its FeatureStore."
