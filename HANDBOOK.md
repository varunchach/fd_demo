# Fraud Detection on RHOAI 3.5 — Reproduction Handbook

Demonstrates platform capabilities on Red Hat OpenShift AI Self-Managed 3.5 /
OpenShift 4.20, using the official Red Hat fraud-detection tutorial
(https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/openshift_ai_tutorial_-_fraud_detection_example)
as the model/data source of truth, plus MLflow, Model Registry, OpenTelemetry/Tempo
and Argo CD wrapped around it to show the full platform surface.

This is a **capability demo, not a fraud solution** — the model is the tutorial's
small Keras network, trained for 2 epochs. Don't judge it on accuracy.

## 0. Prerequisites

- OpenShift Container Platform 4.20+, logged in as a cluster-admin-capable user (`oc whoami`)
- Red Hat OpenShift AI Self-Managed 3.5, with `DataScienceCluster` component
  `aipipelines`, `dashboard`, `feastoperator`, `modelregistry`, `workbenches`
  all `Managed` (check: `oc get dsc default-dsc -o yaml`)
- Cluster-admin ability to: install OLM operators, edit the cluster-scoped
  `DataScienceCluster` and create a cluster-scoped `MLflow`/`ModelRegistry` instance
- A GitHub (or other git host) repo you control, for the GitOps manifests
- Outbound internet access from pods (public PyPI, GitHub, quay.io) — if your
  cluster is air-gapped, substitute your own mirrors for the pip installs below

### Version note
This was verified on OCP 4.20.40 / RHOAI 3.5.1. Exact image digests and package
mirror URLs are specific to this cluster's build; re-resolve them if different.

## 1. Enable platform capabilities (cluster-scoped — needs admin approval)

These three steps are **platform-level changes**. Get explicit sign-off before
running them in a customer environment.

### 1a. Enable the MLflow operator component
```bash
oc patch dsc default-dsc --type=merge -p \
  '{"spec":{"components":{"mlflowoperator":{"managementState":"Managed"}}}}'
```

### 1b. Install OpenTelemetry, Tempo, and OpenShift GitOps operators
Not part of RHOAI itself — official Red Hat operators from the `redhat-operators`
catalog, needed for the tracing and GitOps capabilities.
```bash
oc apply -f - <<'EOF'
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata: {name: opentelemetry-product, namespace: openshift-operators}
spec: {channel: stable, name: opentelemetry-product, source: redhat-operators, sourceNamespace: openshift-marketplace, installPlanApproval: Automatic}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata: {name: tempo-product, namespace: openshift-operators}
spec: {channel: stable, name: tempo-product, source: redhat-operators, sourceNamespace: openshift-marketplace, installPlanApproval: Automatic}
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata: {name: openshift-gitops-operator, namespace: openshift-operators}
spec: {channel: latest, name: openshift-gitops-operator, source: redhat-operators, sourceNamespace: openshift-marketplace, installPlanApproval: Automatic}
EOF
```
Wait for CSVs to reach `Succeeded`: `oc get csv -n openshift-operators | grep -E "opentelemetry|tempo|gitops"`

### 1c. Create the MLflow tracking server instance (cluster-scoped CR)
```bash
oc apply -f - <<'EOF'
apiVersion: mlflow.opendatahub.io/v1
kind: MLflow
metadata: {name: mlflow}
spec:
  backendStoreUri: "sqlite:////mlflow/mlflow.db"
  serveArtifacts: true
  artifactsDestination: "file:///mlflow/artifacts"
  storage: {resources: {requests: {storage: 5Gi}}}
EOF
```
Verify: `oc get mlflow mlflow -o jsonpath='{.status.conditions}'` → `Available: True`.

## 2. Project namespace and storage

```bash
oc apply -f - <<'EOF'
apiVersion: project.openshift.io/v1
kind: Project
metadata:
  name: fraud-detection
  labels: {opendatahub.io/dashboard: "true"}
EOF

oc apply -n fraud-detection -f - <<'EOF'
apiVersion: v1
kind: ServiceAccount
metadata: {name: demo-setup}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: demo-setup-edit}
subjects: [{kind: ServiceAccount, name: demo-setup}]
roleRef: {kind: ClusterRole, name: edit, apiGroup: rbac.authorization.k8s.io}
EOF
```

Download and review the tutorial's storage setup manifest before applying it
(it deploys a small self-hosted S3-compatible service called "s4" plus two
buckets and connection secrets — review it, don't blind-pipe a URL into `oc apply`):
```bash
curl -fsSL -o setup-s3.yaml \
  https://raw.githubusercontent.com/rh-aiservices-bu/fraud-detection/main/setup/setup-s3-no-sa.yaml
oc apply -n fraud-detection -f setup-s3.yaml
```
Wait for the three Jobs (`create-s4-credentials-secret`, `create-ds-connections`,
`create-s4-buckets`) to show `Complete`: `oc get jobs -n fraud-detection`.
This produces two Secrets used later: `my-storage` and `pipeline-artifacts`.

**Purpose of each file:** `setup-s3.yaml` is the tutorial's own asset — it is
*not* an RHOAI component, just a lightweight stand-in for real S3/ODF so the
demo needs no external cloud storage.

## 3. AI Pipelines (DataSciencePipelinesApplication)

```bash
oc apply -n fraud-detection -f - <<'EOF'
apiVersion: datasciencepipelinesapplications.opendatahub.io/v1
kind: DataSciencePipelinesApplication
metadata: {name: pipelines-definition}
spec:
  dspVersion: v2
  apiServer: {deploy: true}
  persistenceAgent: {deploy: true}
  mlmd: {deploy: true}
  objectStorage:
    externalStorage:
      host: s4.fraud-detection.svc.cluster.local:7480
      scheme: http
      bucket: pipeline-artifacts
      secure: false
      s3CredentialsSecret:
        secretName: pipeline-artifacts
        accessKey: AWS_ACCESS_KEY_ID
        secretKey: AWS_SECRET_ACCESS_KEY
EOF
```
Verify: `oc get dspa pipelines-definition -n fraud-detection -o jsonpath='{.status.conditions}'`
— wait for `Ready: True`.

## 4. Workbench

```bash
oc apply -n fraud-detection -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: fraud-detection-workspace}
spec: {accessModes: ["ReadWriteOnce"], resources: {requests: {storage: 5Gi}}}
---
apiVersion: v1
kind: ServiceAccount
metadata: {name: fraud-detection}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: fraud-detection-sa-edit}
subjects: [{kind: ServiceAccount, name: fraud-detection}]
roleRef: {kind: ClusterRole, name: edit, apiGroup: rbac.authorization.k8s.io}
EOF
oc apply -f notebook.yaml   # see file in this repo
```
`notebook.yaml`'s key fields: `opendatahub.io/mlflow-instance: mlflow` annotation
(wires up MLflow env vars automatically), `serviceAccountName: fraud-detection`
(must match the SA above — the MLflow integration's auto-created RoleBinding
targets a SA named after the Notebook, but you must create that SA yourself
when applying CRs directly instead of through the dashboard), `envFrom: my-storage`
(S3 credentials), PVC mount at `/opt/app-root/src`.

Wait for the pod: `oc get pods -n fraud-detection -l app=fraud-detection` (or by name `fraud-detection-0`).

### Clone the tutorial and train
```bash
oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "cd /opt/app-root/src && git clone --branch v3.5 --recurse-submodules \
   https://github.com/rh-aiservices-bu/fraud-detection.git"

# The curated RHOAI pip mirror doesn't carry tensorflow/keras — the tutorial's
# own notebook needs them from public PyPI. Get sign-off for this in a locked-down
# customer environment before running it.
oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "pip install -q --index-url https://pypi.org/simple/ tensorflow==2.21.0 onnxruntime==1.25.1 && \
   pip install -q --no-deps --index-url https://pypi.org/simple/ tf2onnx==1.16.1"

oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "cd /opt/app-root/src/fraud-detection && jupyter nbconvert --to notebook --execute \
   --inplace --ExecutePreprocessor.timeout=900 1_experiment_train.ipynb"
```
**Expected result:** `models/fraud/1/model.onnx` and `artifact/{scaler,test_data}.pkl`
exist under `/opt/app-root/src/fraud-detection/`. We observed accuracy 97.5%,
precision 0.9715, recall 0.7356 — your numbers will vary slightly (random init).

## 5. Log the run to MLflow (Experiments capability)

Copy `scripts/mlflow_log_run.py` from this repo into the workbench and run it:
```bash
cat scripts/mlflow_log_run.py | oc exec -i fraud-detection-0 -n fraud-detection -- \
  bash -c "cat > /opt/app-root/src/fraud-detection/mlflow_log_run.py"
oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "cd /opt/app-root/src/fraud-detection && python mlflow_log_run.py"
```
**What it does:** re-scores the saved test set through the ONNX model, then logs
params/metrics/the ONNX artifact to the MLflow experiment `fraud-detection`
(additive instrumentation — it does not modify the tutorial's own notebook).

**Inspect it:** RHOAI Dashboard → Develop & train → Experiments (MLflow), or
directly at `https://<rhoai-dashboard-gateway-host>/mlflow`.

## 6. Register the model (Model Registry capability)

A Model Registry *instance* (distinct from the platform's `modelregistry`
component) needs its own Postgres-backed CR, created once in the shared
`rhoai-model-registries` namespace:
```bash
oc apply -n rhoai-model-registries -f - <<'EOF'
apiVersion: v1
kind: Secret
metadata: {name: fraud-registry-db}
type: Opaque
stringData: {password: "change-me"}
---
apiVersion: modelregistry.opendatahub.io/v1beta1
kind: ModelRegistry
metadata: {name: fraud-detection-registry}
spec:
  postgres:
    generateDeployment: true
    database: model_registry
    username: registryuser
    passwordSecret: {name: fraud-registry-db, key: password}
EOF

# Grant your workbench SA access to it (per-registry Role, scoped RoleBinding):
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: fraud-detection-workbench-registry-access, namespace: rhoai-model-registries}
subjects: [{kind: ServiceAccount, name: fraud-detection, namespace: fraud-detection}]
roleRef: {kind: Role, name: registry-user-fraud-detection-registry, apiGroup: rbac.authorization.k8s.io}
EOF
```
Then from the workbench:
```bash
oc exec fraud-detection-0 -n fraud-detection -- pip install -q model-registry
cat scripts/register_model.py | oc exec -i fraud-detection-0 -n fraud-detection -- \
  bash -c "cat > /opt/app-root/src/fraud-detection/register_model.py"
oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "cd /opt/app-root/src/fraud-detection && python register_model.py"
```
**Verify:** `https://fraud-detection-registry-rest.<apps-domain>` or RHOAI Dashboard
→ Model Registry → fraud-detection-registry → "fraud-detection" model, version `1.0.0`.

## 7. Run the AI Pipeline

The tutorial ships a pre-compiled KFP v2 pipeline (`5_get_data_train_upload.yaml`,
three steps: get-data → train-model → upload-model). Its `train-model` step uses a
CUDA-enabled TensorFlow runtime image; **if your cluster has a GPU node but the
pod doesn't request it, TensorFlow crashes with a BLAS error.** The fix (same one
the tutorial's own notebook already applies) is a `CUDA_VISIBLE_DEVICES=-1` env var
on that one container — already applied in `scripts/5_get_data_train_upload-cpu-fix.yaml`.
If your cluster has no GPU nodes at all, the original tutorial YAML works unmodified.

```bash
curl -fsSL -o 5_get_data_train_upload.yaml \
  https://raw.githubusercontent.com/rh-aiservices-bu/fraud-detection/v3.5/5_get_data_train_upload.yaml
# apply the CPU fix only if needed (see scripts/5_get_data_train_upload-cpu-fix.yaml for the diff)

cat 5_get_data_train_upload.yaml | oc exec -i fraud-detection-0 -n fraud-detection -- \
  bash -c "cat > /opt/app-root/src/fraud-detection/5_get_data_train_upload.yaml"
oc exec fraud-detection-0 -n fraud-detection -- pip install -q kfp==2.17.0

cat scripts/run_pipeline.py | oc exec -i fraud-detection-0 -n fraud-detection -- \
  bash -c "cat > /opt/app-root/src/fraud-detection/run_pipeline.py"
oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "cd /opt/app-root/src/fraud-detection && python run_pipeline.py"
```
`run_pipeline.py` connects to the DSPA's **in-cluster** API service directly
(`https://ds-pipeline-pipelines-definition.<namespace>.svc.cluster.local:8888`,
trusting the cluster's internal service-CA cert) rather than the external route,
so no separate bearer-token dance is needed from inside the namespace.

**Verify:** RHOAI Dashboard → Pipelines → fraud-detection-train-upload → Runs,
or `oc get pods -n fraud-detection | grep get-data-train-upload` (all `Completed`).
Expected final artifact: `models/fraud/1/model.onnx` in the `my-storage` bucket,
timestamped at the run time.

## 8. Feature Store (Feast)

The Feast feature definitions live in this repo under `feature_repo/` — regenerate
the sample data first if you fork this repo:
```bash
cd feature_repo && python -I generate_data.py
```
Then create the `FeatureStore` CR (it clones this repo's `feature_repo/` path at
startup and runs `feast apply` automatically):
```bash
oc apply -f manifests/featurestore.yaml
```
**Verify ingestion:** `oc get featurestore fraud-feature-store -n fraud-detection -o jsonpath='{.status.phase}'` → `Ready`;
pod logs show `Created entity transaction_id` / `Created feature view fraud_features`.

**Verify retrieval** (materialize once, then query):
```bash
oc exec <feast-pod> -n fraud-detection -c online -- bash -lc \
  "cd /feast-data/fraud_detection/feature_repo && feast materialize-incremental $(date -u +%Y-%m-%dT%H:%M:%S)"
oc exec <feast-pod> -n fraud-detection -c online -- python -c \
  "from feast import FeatureStore; s=FeatureStore(repo_path='.'); \
   print(s.get_online_features(features=['fraud_features:distance_from_last_transaction'], entity_rows=[{'transaction_id':5}]).to_dict())"
```
Feast UI: `https://feast-fraud-feature-store-ui-<namespace>.<apps-domain>`.

## 9. Tracing: OpenTelemetry → Tempo

```bash
oc apply -f manifests/tempo.yaml            # TempoMonolithic, pv-backed, Jaeger UI + route
oc apply -f manifests/otel-collector.yaml   # OpenTelemetryCollector, otlp -> tempo:4317
```
Emit a real trace from the workbench (wraps the tutorial's own "Sally's transaction"
inference example in spans):
```bash
oc exec fraud-detection-0 -n fraud-detection -- pip install -q opentelemetry-sdk opentelemetry-exporter-otlp
cat scripts/emit_trace.py | oc exec -i fraud-detection-0 -n fraud-detection -- \
  bash -c "cat > /opt/app-root/src/fraud-detection/emit_trace.py"
oc exec fraud-detection-0 -n fraud-detection -- bash -lc \
  "cd /opt/app-root/src/fraud-detection && python emit_trace.py"
```
**Verify:** open the Jaeger UI route (`oc get route tempo-fraud-tracing-jaegerui -n fraud-detection`)
in a browser and search for service `fraud-detection-inference`, or query the API directly:
```bash
curl -s 'http://tempo-fraud-tracing-jaegerui.fraud-detection.svc.cluster.local:16686/api/traces?service=fraud-detection-inference'
```
Expect one trace with 4 spans: `fraud-detection-request` (parent), `load-model`,
`load-scaler`, `score-transaction`.

## 10. Argo CD (GitOps)

Fork/clone this repo to your own git remote, then:
```bash
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: argocd-fraud-detection-admin, namespace: fraud-detection}
subjects: [{kind: ServiceAccount, name: openshift-gitops-argocd-application-controller, namespace: openshift-gitops}]
roleRef: {kind: ClusterRole, name: admin, apiGroup: rbac.authorization.k8s.io}
EOF

oc apply -f argocd-application.yaml   # edit repoURL to point at your fork first
```
**Scope note:** this Application manages only `manifests/` (FeatureStore,
TempoMonolithic, OpenTelemetryCollector) — three declarative pieces of demo
*configuration*. It deliberately does **not** manage the Workbench, DSPA, or
Model Registry instance, to keep "GitOps-managed config" and "pipeline
execution" cleanly separated, and to avoid a second controller fighting over
resources that were stood up directly for the earlier steps.

**Verify:** `oc get application fraud-detection-demo -n openshift-gitops -o jsonpath='{.status.sync.status}/{.status.health.status}'`
→ `Synced/Healthy`. Argo CD UI: `https://<openshift-gitops-server-route>`.

## 11. End-to-end walkthrough (for a live demo)

1. Dashboard → Workbenches → open `fraud-detection`, show the cloned repo and the
   executed `1_experiment_train.ipynb` with its accuracy/precision/recall output.
2. Dashboard → Pipelines → show the `fraud-detection-train-upload` run, green, 3 steps.
3. Dashboard → Experiments (MLflow) → `fraud-detection` experiment → run → params/metrics/artifact.
4. Dashboard → Model Registry → `fraud-detection-registry` → model `fraud-detection` v1.0.0.
5. Feast UI → feature view `fraud_features` → sample online values.
6. Jaeger UI → service `fraud-detection-inference` → the 4-span trace.
7. Argo CD UI → `fraud-detection-demo` app → green sync tree of the 3 CRs.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pip install tensorflow` → "No matching distribution" | curated RHOAI mirror doesn't carry it | `--index-url https://pypi.org/simple/` (get approval first) |
| Workbench pod `FailedCreate: serviceaccount not found` | SA referenced in Notebook spec doesn't exist | create the SA explicitly before/with the Notebook CR |
| MLflow `PERMISSION_DENIED` from workbench | pod running as `default` SA, not the one the MLflow RoleBinding targets | set `serviceAccountName` in the Notebook spec to match |
| `train-model` pipeline step: `BLAS operation using StreamExecutor without BLAS support` | GPU-capable node, but pod didn't request the GPU resource | add `CUDA_VISIBLE_DEVICES=-1` env to that step (see §7) |
| Pipeline step fails with `dial tcp 172.30.0.1:443: connect: connection refused` | transient API-server connectivity blip during the Argo executor sidecar's status patch | re-run; KFP v2 caching skips already-completed steps so retries are cheap |
| Argo CD `OutOfSync` forever / `Sync failed ... forbidden` | the `openshift-gitops-argocd-application-controller` SA has no RBAC for the CRD's API group in that namespace | add the per-namespace RoleBinding in §10 |
| `oc apply -f <raw-github-url>` blocked | sandbox/IDE safety policy against piping unreviewed remote content into the cluster | download, read, then `oc apply -f <local-file>` |

## Cleanup (destructive — ask before running)

```bash
# Delete the demo namespace and everything in it (workbench, pipelines, storage, Feast, Tempo, OTel):
oc delete project fraud-detection

# Delete the per-cluster instances created outside that namespace:
oc delete modelregistries.modelregistry.opendatahub.io fraud-detection-registry -n rhoai-model-registries
oc delete secret fraud-registry-db -n rhoai-model-registries
oc delete rolebinding fraud-detection-workbench-registry-access -n rhoai-model-registries
oc delete mlflow mlflow
oc delete application fraud-detection-demo -n openshift-gitops

# Only if nothing else on the cluster needs them, disable the platform-level additions:
oc patch dsc default-dsc --type=merge -p '{"spec":{"components":{"mlflowoperator":{"managementState":"Removed"}}}}'
oc delete subscription opentelemetry-product tempo-product openshift-gitops-operator -n openshift-operators
# (then remove the matching CSVs with `oc get csv -n openshift-operators` / `oc delete csv ...`)
```

## What was verified here vs. what a customer must redo

- Verified on this exact cluster (OCP 4.20.40 / RHOAI 3.5.1, AWS-backed sandbox):
  every step above, with real pods, a real pipeline run, a real MLflow run, a
  real registered model version, a real trace, and a real Argo CD sync.
- A customer must: point `argocd-application.yaml`'s `repoURL` at their own fork;
  get their own sign-off for the three platform-level changes in §1 and the
  public-PyPI exception in §4; re-check whether their pipeline runtime nodes
  have GPUs (affects whether §7's fix is needed); and substitute their own
  object storage / registry passwords instead of the demo defaults used here.
