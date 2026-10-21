#!/usr/bin/env bash
# Install OpenShift GitOps (Argo CD) from Red Hat Operators — one-time cluster admin.
set -euo pipefail

oc apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-gitops-operator
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: openshift-gitops-operator
  namespace: openshift-gitops-operator
spec:
  upgradeStrategy: Default
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-gitops-operator
spec:
  channel: latest
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
EOF

echo "Waiting for openshift-gitops namespace / Argo CD pods..."
for i in $(seq 1 60); do
  if oc get ns openshift-gitops >/dev/null 2>&1 \
     && oc get deploy openshift-gitops-server -n openshift-gitops >/dev/null 2>&1; then
    oc rollout status deploy/openshift-gitops-server -n openshift-gitops --timeout=120s || true
    echo "GitOps installed."
    oc get route -n openshift-gitops 2>/dev/null || true
    exit 0
  fi
  sleep 10
done
echo "Timed out waiting for OpenShift GitOps. Check: oc get csv -A | grep gitops"
exit 1
