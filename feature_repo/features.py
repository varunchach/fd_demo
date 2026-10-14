from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64

transaction = Entity(name="transaction_id", join_keys=["transaction_id"])

transaction_source = FileSource(
    name="transaction_source",
    path="data/transactions.parquet",
    timestamp_field="event_timestamp",
)

fraud_features = FeatureView(
    name="fraud_features",
    entities=[transaction],
    ttl=timedelta(days=3650),
    schema=[
        Field(name="distance_from_last_transaction", dtype=Float32),
        Field(name="ratio_to_median_purchase_price", dtype=Float32),
        Field(name="used_chip", dtype=Int64),
    ],
    source=transaction_source,
)
