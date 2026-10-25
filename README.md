# Fraud MLOps — GitOps demo (`fd-gitops`)

**One command** after env exports: secrets → Argo (DSPA+Feast) → seed/materialize/pipeline.

```bash
export PIPELINE_BUCKET=... FEAST_BUCKET=...   # + AWS_* or SRC_*; + PG_* or PG_SRC_SECRET
./scripts/bootstrap_gitops.sh
```

**Where to see the Argo app / Feature Store UI:** **[docs/WHERE_TO_LOOK.md](docs/WHERE_TO_LOOK.md)**  
(OpenShift Console GitOps / Argo CD UI — **not** inside OpenShift AI.)

Details: **[docs/CLIENT_DEMO.md](docs/CLIENT_DEMO.md)**

| Git (Argo) | Included in `bootstrap_gitops.sh` (not Argo hooks) |
|------------|-----------------------------------------------------|
| DSPA + managed MariaDB (`Replace=true`) | seed / materialize / pipeline submit |
| FeatureStore + S3/Postgres | `run_demo_e2e.sh` step |
