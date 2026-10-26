#!/usr/bin/env bash
# Why Feature Store is (or is not) visible in OpenShift AI → Develop & train → Feature Store.
# RH docs: only ONE cluster FeatureStore may have label feature-store-ui=enabled, and it must be Ready.
set -euo pipefail

NS="${NS:-fd-gitops}"
FS_NAME="${FS_NAME:-fd-gitops-fs}"

echo "======== Feature Store UI visibility ========"

echo "==> 1) feastoperator on DSC"
FEAST=$(oc get dscdefault default -o jsonpath='{.spec.components.feastoperator.managementState}' 2>/dev/null \
  || oc get dsc -A -o jsonpath='{range .items[*]}{.spec.components.feastoperator.managementState}{"\n"}{end}' 2>/dev/null \
  | head -1 || true)
echo "    feastoperator=${FEAST:-unknown}"
[[ "${FEAST}" == "Managed" ]] || echo "    WARN: set feastoperator managementState=Managed in DSC"

echo "==> 2) project labels (Data Science Project)"
oc get ns "$NS" --show-labels | grep -E 'NAME|opendatahub' || true
oc get ns "$NS" -o jsonpath='{.metadata.labels.opendatahub\.io/dashboard}' | grep -q true \
  || { echo "    FAIL: missing opendatahub.io/dashboard=true on $NS"; exit 1; }
echo "    OK dashboard label"

echo "==> 3) FeatureStore in project"
oc get featurestore "$FS_NAME" -n "$NS" -o custom-columns=\
NAME:.metadata.name,PHASE:.status.phase,UI_LABEL:.metadata.labels.feature-store-ui
PHASE=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null || true)
LABEL=$(oc get featurestore "$FS_NAME" -n "$NS" -o jsonpath='{.metadata.labels.feature-store-ui}' 2>/dev/null || true)
[[ "$LABEL" == "enabled" ]] || { echo "    FAIL: need label feature-store-ui=enabled on $FS_NAME"; exit 1; }
[[ "$PHASE" == "Ready" ]] || { echo "    FAIL: phase=$PHASE (UI stays empty until Ready)"; exit 1; }
echo "    OK Ready + UI label"

echo "==> 4) ONLY one UI-enabled FeatureStore cluster-wide (RH constraint)"
oc get featurestore -A -l feature-store-ui=enabled \
  -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,PHASE:.status.phase
COUNT=$(oc get featurestore -A -l feature-store-ui=enabled -o name 2>/dev/null | wc -l | tr -d ' ')
if [[ "${COUNT}" -gt 1 ]]; then
  echo "    WARN: ${COUNT} instances have feature-store-ui=enabled — dashboard uses one; remove label from extras"
fi
OTHER=$(oc get featurestore -A -l feature-store-ui=enabled \
  -o jsonpath="{range .items[?(@.metadata.namespace!=\"${NS}\")]}{.metadata.namespace}/{.metadata.name} {.status.phase}{'\n'}{end}" 2>/dev/null || true)
if [[ -n "${OTHER}" ]]; then
  echo "    WARN: UI label also on other NS (steal/empty UI if Failed):"
  echo "$OTHER" | sed 's/^/      /'
fi

echo "==> 5) Feast UI route/pod"
oc get route,pods -n "$NS" -l "feast.dev/name=${FS_NAME}" 2>/dev/null || \
  oc get route,pods -n "$NS" | grep -E "feast|NAME" || true
ROUTE=$(oc get route -n "$NS" -o name 2>/dev/null | grep -i ui | head -1 || true)
[[ -n "$ROUTE" ]] && echo "    OK $ROUTE" || echo "    WARN: no UI route yet (operator creates after Ready + ui:)"

echo ""
echo "Dashboard path:"
echo "  OpenShift AI → Projects → select '${NS}' → Develop & train → Feature Store"
echo "  (kubeadmin: switch project focus first or the page looks empty)"
echo "======== UI check done ========"
