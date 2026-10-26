# Templated by scripts/configure_argo_site.sh (APP_NAME + NS).
# Do not apply this file directly — run configure_argo_site.sh.
apiVersion: v1
kind: Namespace
metadata:
  name: __NS__
  labels:
    opendatahub.io/dashboard: "true"
    opendatahub.io/feast: "true"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: argocd-__APP_NAME__-admin
  namespace: __NS__
subjects:
  - kind: ServiceAccount
    name: openshift-gitops-argocd-application-controller
    namespace: openshift-gitops
  - kind: ServiceAccount
    name: argocd-argocd-application-controller
    namespace: openshift-gitops
roleRef:
  kind: ClusterRole
  name: admin
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: __APP_NAME__
  namespace: openshift-gitops
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: https://github.com/varunchach/fd_demo.git
    targetRevision: main
    path: chart
    helm:
      valueFiles:
        - values.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: __NS__
  ignoreDifferences:
    - group: datasciencepipelinesapplications.opendatahub.io
      kind: DataSciencePipelinesApplication
      jsonPointers:
        - /status
    - group: feast.dev
      kind: FeatureStore
      jsonPointers:
        - /status
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - RespectIgnoreDifferences=true
      - ApplyOutOfSyncOnly=true
    retry:
      limit: 5
      backoff:
        duration: 30s
        factor: 2
        maxDuration: 5m
