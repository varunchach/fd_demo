# Feature Store visibility in RHOAI 3.5

## NetworkPolicy (required on locked-down client NS)

If the namespace has NetworkPolicies (`allow-same-namespace`, DSPA rules, …),
the RHOAI dashboard in `redhat-ods-applications` cannot reach Feast registry REST
unless allowed. The chart deploys `allow-rhods-dashboard-to-feast` (ports **6573** /
**6571** on pods labeled `feast.dev/name=<featureStore.name>`). Without it the UI
Overview stays empty and `verify_featurestore_ui.sh` times out even when the CR is Ready.

## Credentials (client-owned — do not hardcode)

The chart never embeds Postgres host/port/password or S3 keys. It only
**references** the fixed secret names the client already creates:

| Secret | Purpose | Contents |
| --- | --- | --- |
| `fd-gitops-feast-pg` | Online store | `feature_store.yaml` (`host`, `port`, `database`, `user`, `password`, …) |
| `fd-gitops-feast-s3` | Offline / registry / UI | `AWS_*` keys and endpoint |
| `fd-gitops-pipeline-s3` | Pipelines artifacts | `AWS_*` keys and endpoint |

Create or refresh them with `./scripts/apply_fd_gitops_secrets.sh` using the client's
`PG_*` and `AWS_*` exports (port is required from the client — no default).
Do **not** rename these secrets: the FeatureStore CR `secretRef` names match them
so Feast picks up client credentials automatically.

The Argo Application selects whether its FeatureStore appears in the dashboard.
Only one FeatureStore should have `feature-store-ui=enabled`.

| Application | Helm parameter | Value |
| --- | --- | --- |
| `fd-cust-trial` (the chosen deployment) | `featureStore.uiEnabled` | `true` |
| Other FeatureStore deployments, if retained | `featureStore.uiEnabled` | `false` |

Set these under each Application's Helm parameters in Argo CD, or in its declarative
Application manifest. Use the chart revision containing this fix on all applications.
Review and sync through Argo CD when ready to deploy; editing a local checkout does
not change the cluster. `uiEnabled=false` removes only the dashboard discovery label;
it does not delete the FeatureStore or disable its services.

The default is `true` for compatibility with existing single-instance deployments.
For a new additional deployment, explicitly set it to `false`.

Example fragment to merge into the selected Application's existing parameter list
(keep the other site parameters):

```yaml
spec:
  source:
    helm:
      parameters:
        - name: featureStore.uiEnabled
          value: "true"
```

`configure_argo_site.sh` now preserves existing Helm overrides by name and leaves
an existing Application's repository, revision and destination in place. If using
that deployment script, `FEAST_UI_ENABLED=true` or `false` explicitly changes this
parameter; leaving it unset preserves the existing override. It requires `python3`
for JSON merging. The script still deploys the platform; it is not a read-only
diagnostic. Do not rerun it just to test connectivity.

Make sure the Argo Application's `spec.source.repoURL` and `targetRevision` point
to the repository and revision carrying the fix. A customer fork is a different
source from `varunchach/fd_demo`; changes in one do not update the other. The original
bootstrap Application templates still default to `varunchach/fd_demo`.

## Read-only verification after deployment

```bash
NS=fd-cust-trial FS_NAME=fd-gitops-fs bash scripts/verify_featurestore_ui.sh
```

This script checks both namespace labels, the UI label, the Registry condition,
the REST service, and that only one instance is enabled. It then makes a GET request
to `/api/v1/projects` **from the dashboard container** and checks for `fd_gitops`.
It makes no Kubernetes resource changes. Access to list instances cluster-wide and
execute the diagnostic in the dashboard container is required. The REST probe is
for this chart's `authz.noAuth: true` configuration, and skips certificate validation
only for that diagnostic request. It does not change TLS settings on the cluster.

Override `DASHBOARD_NS`, `DASHBOARD_DEPLOYMENT`, or `DASHBOARD_CONTAINER` if your
dashboard uses non-default names. User permissions in the dashboard must still
allow access to the namespace and FeatureStore; a successful admin probe alone
does not establish another user's access.

The dropdown's Feast project is `fd_gitops`; `fd-cust-trial` is the OpenShift
namespace and `fd-gitops-fs` is the CR name. Do not rename the Feast project or
change registry storage just to change UI visibility.

This change fixes GitOps control of UI discovery. It does not establish that a
previously empty dashboard was caused only by duplicate labels: a failed REST
probe or a missing registry project requires its own diagnosis.

## Local regression checks

With Helm 3, Python 3 and PyYAML installed, run `python3 -m unittest discover -s tests -v`.
These tests render Helm locally and use a fake `oc`; they do not access a cluster.

Reference: [Red Hat OpenShift AI 3.5: Set up the Feature Store UI](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html/working_with_machine_learning_features/overview-of-ml-features-and-feature-store.adoc_featurestore).

