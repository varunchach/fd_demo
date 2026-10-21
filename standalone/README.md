# Standalone Feature Store (S3 ingest) — no Argo CD yet

Flow:

```
1) Secret feast-s3          (MinIO / S3 credentials)
2) Job seed-features-to-s3  (writes parquet to S3)
3) FeatureStore CR          (feast apply reads S3 → online store)
4) Call get-online-features
```

## Apply

```bash
# 0) Namespace
oc create ns fraud-detection
oc label ns fraud-detection opendatahub.io/dashboard=true --overwrite

# 1) S3 secret (copy your MinIO data connection, rename to feast-s3)
oc get secret minio-data-connection -n credit-decisioning -o json \
  | sed 's/"namespace":"[^"]*"/"namespace":"fraud-detection"/; s/"name":"[^"]*"/"name":"feast-s3"/' \
  | oc apply -f -
# Ensure keys: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_ENDPOINT, AWS_S3_BUCKET

# 2) Seed parquet into S3
oc apply -f standalone/seed-s3-job.yaml
oc wait --for=condition=complete job/seed-features-to-s3 -n fraud-detection --timeout=300s

# 3) Feature Store (clones feature_repo from Git, reads S3 path in features.py)
oc apply -f standalone/featurestore.yaml
oc get featurestore -n fraud-detection -w
# STATUS → Ready
```

## Verify

```bash
oc get svc feast-fraud-feature-store-online -n fraud-detection
# Online features URL:
# https://feast-fraud-feature-store-online.fraud-detection.svc.cluster.local:443/get-online-features
```

## Important

- `feature_repo/features.py` must be on GitHub `main` (FeatureStore clones it).
- Data lives in S3: `s3://$AWS_S3_BUCKET/fraud-detection/features/transactions.parquet`
