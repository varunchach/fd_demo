# GitOps demo — independent greenfield stack (`fd-gitops`)

This demo is **new and isolated**. It does **not** reuse namespace `fraud-detection`, DSPA `dspa`, or any prior FeatureStore / secrets / jobs.

| Item | Value |
|------|--------|
| Namespace | `fd-gitops` |
| Argo Application | `fd-gitops` |
| DSPA | `fd-gitops-dspa` → Service `ds-pipeline-fd-gitops-dspa` |
| FeatureStore | `fd-gitops-fs` (Feast project `fd_gitops`) |
| MariaDB (DSPA meta) | `fd-gitops-db` |
| Secrets | `fd-gitops-pipeline-s3`, `fd-gitops-feast-s3`, `fd-gitops-feast-pg` |
| Pipeline | `fd-gitops-pipeline` |
| PostSync Jobs | `fd-gitops-seed-offline` → `fd-gitops-materialize-online` → `fd-gitops-submit-pipeline` |

Leave `fraud-detection` alone for comparison; tear down with Argo delete of `fd-gitops`.

---

## 1. Fill secrets (new names only)

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo

vi examples/secrets/fd-gitops-pipeline-s3.yaml   # bucket fd-gitops-pipeline
vi examples/secrets/fd-gitops-feast-s3.yaml      # bucket fd-gitops-features + AWS_ENDPOINT_URL
vi examples/secrets/fd-gitops-feast-pg.yaml      # dedicated DB fd_gitops recommended
vi chart/values.yaml                            # s3Host + registryS3Path if needed

oc new-project fd-gitops 2>/dev/null || oc project fd-gitops
oc label ns fd-gitops opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite
oc apply -f examples/secrets/ -n fd-gitops
```

Use **new** S3 prefixes (`fd-gitops/...`) and ideally a **new** Postgres database so you are not reading leftover Feast online rows from earlier tests.

## 2. Sync with Argo CD

```bash
oc apply -f argocd/application.yaml
oc get application fd-gitops -n openshift-gitops -w
```

## 3. Watch PostSync

```bash
oc get jobs -n fd-gitops
oc logs -n fd-gitops -l job-name=fd-gitops-seed-offline --tail=30
oc logs -n fd-gitops -l job-name=fd-gitops-materialize-online --tail=40
oc logs -n fd-gitops -l job-name=fd-gitops-submit-pipeline --tail=40
oc get workflow -n fd-gitops
```

## Sync waves

```
wave 0   fd-gitops-db (MariaDB)
wave 1   DSPA fd-gitops-dspa
wave 2   FeatureStore fd-gitops-fs
wave 3   SA fd-gitops-submitter + materialize ConfigMap
PostSync 10  seed offline parquet
PostSync 20  materialize online
PostSync 30  submit pipeline run
```

## Tear down

```bash
oc delete application fd-gitops -n openshift-gitops
# optional: oc delete project fd-gitops
```

`fraud-detection` is untouched.
