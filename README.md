# Fraud Detection Demo — RHOAI 3.5

A simple, self-contained fraud-detection capability demo for Red Hat OpenShift AI 3.5.
No deep learning, no external datasets — synthetic data, a scikit-learn model,
and the platform wired around it: MLflow, AI Pipelines, Model Registry,
OpenTelemetry/Tempo, and Argo CD.

```
notebook/   fraud_detection.ipynb  - ingest -> process -> split -> train -> evaluate -> MLflow
pipeline/   pipeline.py            - same 3 steps as a KFP pipeline (ingest / train+MLflow / register+OTel)
            pipeline.yaml          - compiled pipeline, ready to import
chart/      Helm chart             - deploys the workbench, DSPA, Tempo, OTel Collector, Model Registry
argocd/     application.yaml      - Argo CD Application pointing at chart/
```

## Prerequisites (one-time, cluster admin)

1. OpenShift AI 3.5 with these DataScienceCluster components `Managed`:
   `aipipelines`, `dashboard`, `workbenches`, `modelregistry`, `mlflowoperator`.
2. A cluster-scoped MLflow instance exists and is `Available`:
   ```bash
   oc get mlflow
   ```
   If not, see the one-line fix: `oc patch dsc default-dsc --type=merge -p '{"spec":{"components":{"mlflowoperator":{"managementState":"Managed"}}}}'`
   then create an `MLflow` instance CR (ask your platform admin — this is a
   cluster-scoped change).
3. Tempo Operator and OpenTelemetry Operator installed (`redhat-operators` catalog,
   not part of RHOAI itself — ask your admin to install `tempo-product` and
   `opentelemetry-product` subscriptions if `oc get csv -A | grep -iE "tempo|opentelemetry"`
   is empty).
4. OpenShift GitOps (Argo CD) installed, if you want the GitOps step.
5. A project namespace with the two storage connections already created
   (via RHOAI Dashboard -> Data Connections, or the official tutorial's setup
   script): Secrets named `my-storage` and `pipeline-artifacts`.

## Deploy

```bash
git clone https://github.com/varunchach/fd_demo.git
cd fd_demo
helm install fraud-detection-demo ./chart -n fraud-detection --create-namespace
```

That's it — this creates the workbench (which auto-clones this repo), the
pipeline server, Tempo, the OpenTelemetry Collector, and a Model Registry
instance. Follow the printed NOTES for what to check next.

## Run the pipeline

Compile (only needed if you change `pipeline.py`):
```bash
pip install kfp
python pipeline/pipeline.py
```
Import `pipeline/pipeline.yaml` via RHOAI Dashboard -> Pipelines -> Import
pipeline, then Actions -> Create run. Set the `mlflow_tracking_uri` parameter
to your dashboard's MLflow URL (shown in the workbench's `MLFLOW_TRACKING_URI`
env var) and `registry_server_address` to your Model Registry's route.

## GitOps (optional)

```bash
# one-time: let Argo CD manage resources in this namespace
oc apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: {name: argocd-fraud-detection-admin, namespace: fraud-detection}
subjects: [{kind: ServiceAccount, name: openshift-gitops-argocd-application-controller, namespace: openshift-gitops}]
roleRef: {kind: ClusterRole, name: admin, apiGroup: rbac.authorization.k8s.io}
EOF

oc apply -f argocd/application.yaml
```
From here on, changes to `chart/` in this repo sync automatically — you
don't need to re-run `helm install` by hand after the first time.

## Cleanup (destructive)

```bash
helm uninstall fraud-detection-demo -n fraud-detection
oc delete application fraud-detection-demo -n openshift-gitops   # if GitOps was set up
oc delete modelregistries.modelregistry.opendatahub.io fraud-detection-registry -n rhoai-model-registries
```
