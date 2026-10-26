"""Fraud transaction risk features for BFSI card-fraud scoring.

Shown in RHOAI Feature Store UI (not Feast's default driver demo).
Offline source is a local parquet under feature_repo/data so feast apply
works at pod init without S3. Pipeline / seed jobs can still write S3 later.
"""
from datetime import timedelta
from pathlib import Path

from feast import Entity, FeatureService, FeatureView, Field, FileSource
from feast.types import Float32, Int64

_REPO = Path(__file__).resolve().parent
_PARQUET = _REPO / "data" / "transactions.parquet"

transaction = Entity(
    name="transaction_id",
    join_keys=["transaction_id"],
    description="Payment / card transaction id under fraud review",
)

transaction_source = FileSource(
    name="txn_offline_parquet",
    path=str(_PARQUET),
    timestamp_field="event_timestamp",
    description="Offline history of transaction risk signals",
)

fraud_txn_risk_signals = FeatureView(
    name="fraud_txn_risk_signals",
    entities=[transaction],
    ttl=timedelta(days=3650),
    description=(
        "Card-fraud risk signals for one transaction: geo jump, spend anomaly, "
        "chip/PIN, e-commerce channel, and merchant familiarity"
    ),
    tags={"domain": "fraud", "use_case": "card_transaction_scoring"},
    schema=[
        Field(
            name="geo_distance_from_last_txn",
            dtype=Float32,
            description="Distance from the customer's previous txn (km). Large jumps → possible stolen-card use.",
        ),
        Field(
            name="spend_vs_median_ratio",
            dtype=Float32,
            description="Txn amount ÷ customer's median spend. High ratio → unusual ticket size.",
        ),
        Field(
            name="card_chip_present",
            dtype=Int64,
            description="1 = EMV chip used (card-present). 0 = magstripe/other.",
        ),
        Field(
            name="pin_authenticated",
            dtype=Int64,
            description="1 = PIN verified at POS. 0 = no PIN.",
        ),
        Field(
            name="ecommerce_channel",
            dtype=Int64,
            description="1 = online / e-commerce. 0 = in-store.",
        ),
        Field(
            name="known_merchant_repeat",
            dtype=Int64,
            description="1 = customer has shopped this merchant before. 0 = first time.",
        ),
    ],
    source=transaction_source,
)

fraud_scoring_service = FeatureService(
    name="fraud_scoring_service",
    features=[fraud_txn_risk_signals],
    description="Online feature bundle for fraud model training and real-time scoring",
    tags={"pipeline": "fd-gitops", "consumer": "kfp_train"},
)
