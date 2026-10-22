# Fraud MLOps — independent GitOps demo (`fd-gitops`)

Greenfield Argo CD stack. **Does not reuse** `fraud-detection`, existing `dspa`, or old secrets.

| Layer | What |
|-------|------|
| Namespace | `fd-gitops` |
| Argo | Application `fd-gitops` syncs `chart/` |
| PostSync | seed → materialize → submit |
| Secrets | `fd-gitops-pipeline-s3`, `fd-gitops-feast-s3`, `fd-gitops-feast-pg` |

## Start

**[docs/GITOPS_DEMO.md](docs/GITOPS_DEMO.md)**

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
# fill examples/secrets/fd-gitops-*.yaml + chart/values.yaml
oc apply -f examples/secrets/ -n fd-gitops
oc apply -f argocd/application.yaml
```

CLI (no Argo): `./scripts/oneshot.sh` → same `fd-gitops` namespace.
