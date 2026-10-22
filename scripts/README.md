# Helper scripts

| Script | Purpose |
|--------|---------|
| `seed_feast_s3.py` | Used by `feature_repo/seed-s3-job.yaml` (ConfigMap) to upload parquet |
| `submit_pipeline_run.py` | Upload KFP YAML + create a run against DSPA |
| `submit-fraud-pipeline-job.yaml` | Job wrapper for the submitter |
| `submitter-rbac.yaml` | SA + RoleBinding for DSPA API |
| `materialize_online.py` | Optional: boto3 → `write_to_online_store` (no s3fs) |
| `apply_feature_service.py` / `create_saved_dataset.py` | Optional catalog bootstrap |

Typical post-sync:

```bash
oc apply -f feature_repo/seed-s3-job.yaml
oc apply -f scripts/submitter-rbac.yaml
oc create configmap fraud-mlops-pipeline-yaml -n fraud-mlops \
  --from-file=pipeline.yaml=../pipeline/pipeline.yaml --dry-run=client -o yaml | oc apply -f -
oc create configmap feast-submit-script -n fraud-mlops \
  --from-file=submit_pipeline_run.py=submit_pipeline_run.py --dry-run=client -o yaml | oc apply -f -
oc apply -f submit-fraud-pipeline-job.yaml
```
