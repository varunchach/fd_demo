# One-shot CLI deploy (no Argo)

Namespace: **fraud-detection**. Prefer **[GITOPS_DEMO.md](GITOPS_DEMO.md)** when OpenShift GitOps is available.

## Once: fill secrets + chart values

```bash
git clone https://github.com/varunchach/fd_demo.git && cd fd_demo

vi examples/secrets/pipeline-artifacts.yaml
vi examples/secrets/feast-offline-s3.yaml
vi examples/secrets/feast-online-postgres.yaml
vi chart/values.yaml

oc new-project fraud-detection 2>/dev/null || oc project fraud-detection
oc apply -f examples/secrets/ -n fraud-detection
```

## Deploy + seed + materialize + submit

```bash
chmod +x scripts/oneshot.sh scripts/materialize_online.sh
./scripts/oneshot.sh
```

## GitOps-only platform, then oneshot for data path

```bash
oc apply -f argocd/application.yaml   # Argo syncs chart/ (hooks may already run)
# Or disable hooks in values, sync platform, then:
./scripts/oneshot.sh
```

## What owns what

| GitOps (chart / Argo) | oneshot.sh |
|----------------------|------------|
| DSPA, MariaDB, FeatureStore, hook Jobs | Same via helm + seed Job + materialize exec + submit Job |
