# Fraud feature dictionary (business meaning)

These are the features clients see under **Feature Store** (not Feast’s sample `driver_hourly_stats`).

| Feature | Type | Unit / range | Business interpretation |
|---------|------|--------------|-------------------------|
| **transaction_id** (entity) | id | — | One payment / card transaction under review |
| **geo_distance_from_last_txn** | float | km · typical 0–50 local; >500 geo jump | How far this txn is from the customer’s previous one. Large jump → possible stolen card used elsewhere. |
| **spend_vs_median_ratio** | float | ratio · typical 0.5–2; >5 unusual | Amount ÷ customer’s median spend. Spike → unusual ticket / burst fraud. |
| **card_chip_present** | 0/1 | 1 = EMV chip; 0 = magstripe/CNP | EMV chip used at POS (card-present). Chip lowers skimming risk. |
| **pin_authenticated** | 0/1 | 1 = PIN OK; 0 = no PIN | PIN verified. Supports legitimate cardholder present. |
| **ecommerce_channel** | 0/1 | 1 = online; 0 = in-store | Online order. Higher card-not-present fraud exposure. |
| **known_merchant_repeat** | 0/1 | 1 = seen before; 0 = first-time | Customer has used this merchant before. First-time merchants add risk. |

**Feature view:** `fraud_txn_risk_signals` — risk signals at transaction time  
**Feature service:** `fraud_scoring_service` — what the KFP pipeline pulls for train/score  
**Online refs:** `fraud_txn_risk_signals:<feature_name>` (e.g. `fraud_txn_risk_signals:spend_vs_median_ratio`)

Offline: S3 parquet · Online: PostgreSQL · Registry: S3 (customer) / local (lab until seeded)

Demo seed (`scripts/seed_feast_s3.py`) generates **interpretable** values in these units (not random Gaussian blobs), so Feature Store samples and dashboards read as a real fraud scorecard.
