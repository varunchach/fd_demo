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
    # Replaced by configure_argo_site.sh (__GIT_REPO_URL__ / __GIT_REVISION__).
    # Customer fork URL — also set as Helm param git.repoURL so Feast clones the same repo.
    repoURL: __GIT_REPO_URL__
    targetRevision: __GIT_REVISION__
    path: chart
    helm:
      valueFiles:
        - values.yaml
      parameters:
        - name: git.repoURL
          value: __GIT_REPO_URL__
        - name: git.revision
          value: __GIT_REVISION__
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

