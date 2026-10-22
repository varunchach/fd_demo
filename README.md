# Fraud MLOps — independent GitOps demo (`fd-gitops`)

Greenfield Argo CD stack. **Does not reuse** `fraud-detection`, existing `dspa`, or old secrets.

| Layer | What |
|-------|------|
| Namespace | `fd-gitops` |
| Argo | Application `fd-gitops` syncs `chart/` |
| PostSync | seed → materialize → submit |
| Secrets | `fd-gitops-pipeline-s3`, `fd-gitops-feast-s3`, `fd-gitops-feast-pg` |

## Start

**Client walkthrough:** **[docs/CLIENT_DEMO.md](docs/CLIENT_DEMO.md)**  
**Technical GitOps detail:** **[docs/GITOPS_DEMO.md](docs/GITOPS_DEMO.md)**

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
# set chart/values.yaml s3Host + buckets, push
export PG_HOST=... PG_USER=... PG_PASSWORD=...
./scripts/apply_fd_gitops_secrets.sh    # dual S3 (new buckets) + fresh Postgres
oc apply -f argocd/application.yaml     # GitOps → Applications → fd-gitops
```

CLI (no Argo): `./scripts/oneshot.sh` → same `fd-gitops` namespace.
