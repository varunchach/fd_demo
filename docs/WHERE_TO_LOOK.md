# Where to see GitOps / Feature Store (do not look in the wrong UI)

## 1) Argo CD Application — **not** inside OpenShift AI

OpenShift AI (RHOAI) has **no** GitOps applications list. GitOps lives in the **OpenShift Console** or the **Argo CD UI**.

### A. OpenShift Console — GitOps plugin (Administrator)

1. OpenShift Console → switch to **Administrator** perspective  
2. Left nav → **GitOps** → **Applications**  
3. Project filter: **`openshift-gitops`** (not `fd-gitops`)  
4. You should see Application **`fd-gitops`**

If **GitOps** is missing from the left nav, enable the console plugin:

```bash
# list current plugins
oc get console.operator.openshift.io cluster -o jsonpath='{.spec.plugins}{"\n"}'

# enable gitops-plugin (merge; keep existing plugins)
oc patch console.operator.openshift.io cluster --type merge -p \
  '{"spec":{"plugins":["networking-console-plugin","monitoring-plugin","pipelines-console-plugin","distributed-tracing-console-plugin","gitops-plugin"]}}'
```

Refresh the browser (hard refresh). Still missing? Use path B.

### B. Argo CD UI (always works)

```bash
oc get route openshift-gitops-server -n openshift-gitops \
  -o jsonpath='https://{.spec.host}{"\n"}'
```

Or: OpenShift Console → **Red Hat Applications** (waffle) → **Cluster Argo CD**  
Log in with OpenShift. Open app **`fd-gitops`**.

### C. Wrong place (empty on purpose)

| You opened | Why empty |
|------------|-----------|
| Project **`fd-gitops`** → Applications | Application CR lives in **`openshift-gitops`** |
| OpenShift AI dashboard → looking for “GitOps” | RHOAI has no Argo apps page |

```bash
# correct
oc get applications.argoproj.io -n openshift-gitops

# will look empty / wrong
oc get applications.argoproj.io -n fd-gitops
```

---

## 2) Feature Store — **is** inside OpenShift AI

1. OpenShift AI → **Projects** → select **`fd-gitops`**  
2. **Develop & train** → **Feature Store**

Requirements (all must be true):

- DSC `feastoperator: Managed`
- NS label `opendatahub.io/dashboard=true`
- FeatureStore `fd-gitops-fs` phase **Ready**
- Label `feature-store-ui: enabled` on that CR  
- **Only one** FeatureStore cluster-wide should have that UI label (RH rule)

```bash
./scripts/verify_featurestore_ui.sh
```
