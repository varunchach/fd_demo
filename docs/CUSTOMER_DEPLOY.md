# Customer notes (greenfield `fd-gitops`)

Use **docs/GITOPS_DEMO.md**. This stack is independent:

- Namespace `fd-gitops`
- Own DSPA `fd-gitops-dspa`, FeatureStore `fd-gitops-fs`, MariaDB `fd-gitops-db`
- Secrets `fd-gitops-pipeline-s3`, `fd-gitops-feast-s3`, `fd-gitops-feast-pg`

Do **not** point this chart at an existing DSPA named `dspa`. Use fresh S3 prefixes and a dedicated Postgres DB for clean tests.
