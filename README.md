# Fraud Detection MLOps (fd_demo)

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
```

## Standalone Feature Store (S3 -> Feast)

```bash
oc create ns fraud-detection
oc label ns fraud-detection opendatahub.io/dashboard=true --overwrite

# Secret feast-s3 must have: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT, AWS_S3_BUCKET
oc apply -f feature_repo/seed-s3-job.yaml
oc wait --for=condition=complete job/seed-features-to-s3 -n fraud-detection --timeout=300s

oc apply -f feature_repo/featurestore.yaml
oc get featurestore -n fraud-detection   # Ready
```

Online: `https://feast-fraud-feature-store-online.fraud-detection.svc.cluster.local:443/get-online-features`

## Argo CD (later)

`oc apply -f argocd/application.yaml`  (deploys chart/ into fraud-mlops or update ns)
