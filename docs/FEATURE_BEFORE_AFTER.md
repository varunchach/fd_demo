# Before vs after — new Feature Store field

Demo change: add **`txn_velocity_1h`** (txns in the last 1 hour) to
`fraud_txn_risk_signals`.

## Before (UI)

OpenShift AI → project → Feature Store → project **`fd_gitops`** →
feature view **`fraud_txn_risk_signals`**

| Features (6) |
| --- |
| geo_distance_from_last_txn |
| spend_vs_median_ratio |
| card_chip_present |
| pin_authenticated |
| ecommerce_channel |
| known_merchant_repeat |

**No** `txn_velocity_1h`.

## After (code)

In `feature_repo/features.py` the view schema gains:

```python
Field(
    name="txn_velocity_1h",
    dtype=Int64,
    description="Count of card txns in the last 1 hour. Burst velocity → stolen-card testing.",
),
```

Same name is listed in `feature_catalog.py`, `scripts/seed_feast_s3.py`, and
`docs/FEATURE_DICTIONARY.md`. Offline parquet includes the column.

## After (UI — what you should see)

Same path; feature view **`fraud_txn_risk_signals`** now lists **7** features,
including:

| New feature | Type | Meaning |
| --- | --- | --- |
| **txn_velocity_1h** | Int64 | 1h card velocity; high → burst fraud |

## Apply on the cluster (client)

1. Sync Git / Argo so Feast clones the updated `feature_repo` (`main` with this commit).
2. Restart Feast apply (or delete the Feast pod so init re-runs `feast apply`):
   ```bash
   oc delete pod -n fd-cust-trial -l feast.dev/name=fd-gitops-fs
   oc rollout status deploy -n fd-cust-trial -l feast.dev/name=fd-gitops-fs
   ```
3. Re-seed offline parquet (adds the new column in S3):
   ```bash
   NS=fd-cust-trial ./scripts/run_demo_e2e.sh
   # or only the seed job from feature_repo/seed-s3-job.yaml
   ```
4. Refresh Feature Store UI → confirm **`txn_velocity_1h`** appears.

Online materialize is required only if you need the new field in the online store
for scoring — registry/UI discovery of the schema comes from `feast apply`.

