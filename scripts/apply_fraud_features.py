"""Register fraud feature views into the Feast feature repo (run inside Feast pod)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from feast import Entity, FeatureService, FeatureStore, FeatureView, Field, FileSource
from feast.types import Float32, Int64

repo = Path("/feast-data/fd_gitops/feature_repo")
data = repo / "data"
data.mkdir(parents=True, exist_ok=True)

for p in list(data.glob("driver_*.parquet")) + [
    repo / "feature_definitions.py",
    repo / "test_workflow.py",
]:
    if p.exists():
        p.unlink()

rng = np.random.default_rng(42)
n = 100
fraud = rng.random(n) < 0.1
geo = np.where(fraud, rng.uniform(200, 4000, n), rng.exponential(12.0, n).clip(0, 80))
spend = np.where(fraud, rng.uniform(4.0, 18.0, n), rng.lognormal(0.0, 0.35, n).clip(0.2, 3.5))
ecommerce = np.where(fraud, 1, (rng.random(n) < 0.35).astype(int))
chip = np.where(ecommerce == 1, 0, (rng.random(n) < 0.85).astype(int))
pin = np.where((chip == 1) & (ecommerce == 0), (rng.random(n) < 0.9).astype(int), 0)
known = np.where(fraud, 0, (rng.random(n) < 0.7).astype(int))
now = datetime.now(timezone.utc)
df = pd.DataFrame(
    {
        "transaction_id": np.arange(n, dtype="int64"),
        "event_timestamp": [now - timedelta(minutes=(n - i)) for i in range(n)],
        "geo_distance_from_last_txn": geo.astype("float32"),
        "spend_vs_median_ratio": spend.astype("float32"),
        "card_chip_present": chip.astype("int64"),
        "pin_authenticated": pin.astype("int64"),
        "ecommerce_channel": ecommerce.astype("int64"),
        "known_merchant_repeat": known.astype("int64"),
    }
)
parquet = data / "transactions.parquet"
df.to_parquet(parquet, index=False)

transaction = Entity(
    name="transaction_id",
    join_keys=["transaction_id"],
    description="Payment transaction under fraud review",
)
transaction_source = FileSource(
    name="txn_offline_parquet",
    path=str(parquet),
    timestamp_field="event_timestamp",
)
fraud_txn_risk_signals = FeatureView(
    name="fraud_txn_risk_signals",
    entities=[transaction],
    ttl=timedelta(days=3650),
    description="Card-fraud risk signals at transaction time",
    tags={"domain": "fraud"},
    schema=[
        Field(name="geo_distance_from_last_txn", dtype=Float32, description="km from last txn"),
        Field(name="spend_vs_median_ratio", dtype=Float32, description="amount / median spend"),
        Field(name="card_chip_present", dtype=Int64, description="1=EMV chip"),
        Field(name="pin_authenticated", dtype=Int64, description="1=PIN OK"),
        Field(name="ecommerce_channel", dtype=Int64, description="1=online"),
        Field(name="known_merchant_repeat", dtype=Int64, description="1=known merchant"),
    ],
    source=transaction_source,
)
fraud_scoring_service = FeatureService(
    name="fraud_scoring_service",
    features=[fraud_txn_risk_signals],
    description="Fraud scoring feature bundle",
)

# Persist definitions so feast-apply / restarts keep them
(repo / "features.py").write_text(
    Path(__file__).read_text(encoding="utf-8")
    if False
    else f'''from datetime import timedelta
from feast import Entity, FeatureService, FeatureView, Field, FileSource
from feast.types import Float32, Int64

transaction = Entity(name="transaction_id", join_keys=["transaction_id"], description="Payment transaction under fraud review")
transaction_source = FileSource(name="txn_offline_parquet", path="{parquet.as_posix()}", timestamp_field="event_timestamp")
fraud_txn_risk_signals = FeatureView(
    name="fraud_txn_risk_signals",
    entities=[transaction],
    ttl=timedelta(days=3650),
    description="Card-fraud risk signals at transaction time",
    tags={{"domain": "fraud"}},
    schema=[
        Field(name="geo_distance_from_last_txn", dtype=Float32, description="km from last txn"),
        Field(name="spend_vs_median_ratio", dtype=Float32, description="amount / median spend"),
        Field(name="card_chip_present", dtype=Int64, description="1=EMV chip"),
        Field(name="pin_authenticated", dtype=Int64, description="1=PIN OK"),
        Field(name="ecommerce_channel", dtype=Int64, description="1=online"),
        Field(name="known_merchant_repeat", dtype=Int64, description="1=known merchant"),
    ],
    source=transaction_source,
)
fraud_scoring_service = FeatureService(name="fraud_scoring_service", features=[fraud_txn_risk_signals], description="Fraud scoring feature bundle")
'''
)

reg = Path("/feast-data/registry.db")
if reg.exists():
    reg.unlink()

store = FeatureStore(repo_path=str(repo))
store.apply([transaction, fraud_txn_risk_signals, fraud_scoring_service])
print("views", [v.name for v in store.list_feature_views()])
print("services", [s.name for s in store.list_feature_services()])
print("features", [f.name for f in fraud_txn_risk_signals.features])
