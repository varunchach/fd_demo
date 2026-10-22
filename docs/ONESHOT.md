# CLI path (same greenfield stack, no Argo)

Namespace: **`fd-gitops`**. Prefer **[GITOPS_DEMO.md](GITOPS_DEMO.md)** with Argo.

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo
vi examples/secrets/fd-gitops-*.yaml
vi chart/values.yaml
oc apply -f examples/secrets/ -n fd-gitops
chmod +x scripts/oneshot.sh scripts/materialize_online.sh
./scripts/oneshot.sh
```
