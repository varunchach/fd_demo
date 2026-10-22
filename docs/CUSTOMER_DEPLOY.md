# Customer deploy from scratch — Postgres + dual S3

## Architecture (what the client asked for)

| Concern | Store | Secret / config |
|---------|--------|-----------------|
| **Pipeline artifacts** (DSPA runs, datasets) | **S3 #1** | `pipeline-artifacts` + `chart/values.yaml` `pipelines.s3*` |
| **Feast offline** (parquet FileSource) | **S3 #2** | `feast-offline-s3` + `features.py` path |
| **Feast registry** | **S3 #2** (or same account, path in values) | `featureStore.registryS3Path` |
| **Feast online** | **PostgreSQL** | `feast-online-postgres` |
| **DSPA metadata DB** | **MySQL/MariaDB** (RHOAI requirement — not Postgres) | lab: chart MariaDB; prod: `pipelines.externalDb` |

> OpenShift AI **DSPA does not use Postgres** for its metadata DB. Feast **online** is where customer Postgres goes.

```
                    ┌─────────────────────┐
  pipeline runs ──► │ S3 pipeline-artifacts│
                    └─────────────────────┘
  feast apply / UI ─► S3 registry.db
  feast offline   ─► S3 …/transactions.parquet
  get-online-features ► PostgreSQL (online store)
```

---

## 0. Platform (cluster admin, once)

Enable in OpenShift AI / DSC: **Feast**, **Data Science Pipelines**, **MLflow**.  
Do **not** install Feast/Postgres/S3 with this Helm chart.

---

## 1. Clone

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
export NS=fraud-mlops   # or customer project name
oc new-project $NS 2>/dev/null || oc project $NS
oc label ns $NS opendatahub.io/dashboard=true opendatahub.io/feast=true --overwrite
```

---

## 2. Create the three secrets (fill real values)

```bash
# Edit files under examples/secrets/ then:
oc apply -f examples/secrets/pipeline-artifacts.yaml -n $NS
oc apply -f examples/secrets/feast-offline-s3.yaml -n $NS
oc apply -f examples/secrets/feast-online-postgres.yaml -n $NS
```

**Postgres secret** (`feast-online-postgres`) must contain key `feature_store.yaml` with:

```yaml
online_store:
  type: postgres
  host: <pg-host>
  port: 5432
  database: feast
  db_schema: public
  user: <user>
  password: <password>
  sslmode: require    # or disable for lab
```

---

## 3. Edit `chart/values.yaml`

```yaml
pipelines:
  s3Host: <pipeline-s3-hostname>      # no https://
  s3Port: "443"
  s3Scheme: https
  s3Bucket: pipeline-artifacts
  artifactsSecret: pipeline-artifacts
  deployMariaDB: true                 # false if customer provides MySQL for DSPA
  # externalDb: ...                   # when deployMariaDB: false

featureStore:
  onlinePostgresSecret: feast-online-postgres
  offlineS3Secret: feast-offline-s3
  offlineS3Prefix: fraud-detection/features
  registryS3Path: s3://<feast-bucket>/fraud-detection/registry.db
```

`registryS3Path` bucket must be reachable with credentials in `feast-offline-s3`.

---

## 4. Deploy chart

```bash
# GitOps
oc apply -f argocd/application.yaml

# or Helm
helm upgrade --install fraud-mlops ./chart -n $NS
```

Wait:

```bash
oc get dspa,featurestore -n $NS
# Ready
```

---

## 5. Seed offline parquet (S3 #2)

```bash
sed -i "s/namespace: fraud-mlops/namespace: $NS/g" feature_repo/seed-s3-job.yaml
oc apply -f feature_repo/seed-s3-job.yaml
oc wait -n $NS --for=condition=complete job/seed-features-to-s3 --timeout=300s
```

---

## 6. Run pipeline

Upload `pipeline/pipeline.yaml` in OpenShift AI → Pipelines (DSPA `fraud-detection-dspa`).

Parameters:

| Param | Source |
|-------|--------|
| `s3_*` / AWS keys | **pipeline-artifacts** S3 |
| `feast_online_server_url` | `https://feast-fraud-feature-store-online.$NS.svc.cluster.local:443` |
| `mlflow_tracking_uri` | `https://mlflow.redhat-ods-applications.svc.cluster.local:8443/mlflow` |

---

## 7. Verify

```bash
oc get featurestore,dspa -n $NS
oc get workflow -n $NS
# Feature store UI → Develop & train → Feature store
```

---

## Lab vs customer

| | Lab (`deployMariaDB: true`) | Customer |
|--|------------------------------|----------|
| Feast online | still Postgres secret (or change to sqlite for tiny labs) | **Postgres** |
| Feast offline + registry | S3 | **S3** |
| Pipeline artifacts | S3 | **S3** |
| DSPA DB | chart MariaDB | customer **MySQL/MariaDB** |
