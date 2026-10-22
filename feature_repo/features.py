import os
from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource
from feast.types import Float32, Int64

_bucket = os.environ.get("AWS_S3_BUCKET", "pipeline-artifacts")
_prefix = os.environ.get("FEAST_S3_PREFIX", "fraud-detection/features").strip("/")
_endpoint = os.environ.get("AWS_S3_ENDPOINT", "http://minio.fraud-detection.svc.cluster.local:9000")

transaction = Entity(name="transaction_id", join_keys=["transaction_id"])

transaction_source = FileSource(
    name="transaction_source",
    path=f"s3://{_bucket}/{_prefix}/transactions.parquet",
    timestamp_field="event_timestamp",
    s3_endpoint_override=_endpoint,
)

fraud_features = FeatureView(
    name="fraud_features",
    entities=[transaction],
    ttl=timedelta(days=3650),
    schema=[
        Field(name="distance_from_last_transaction", dtype=Float32),
        Field(name="ratio_to_median_purchase_price", dtype=Float32),
        Field(name="used_chip", dtype=Int64),
        Field(name="used_pin_number", dtype=Int64),
        Field(name="online_order", dtype=Int64),
        Field(name="repeat_retailer", dtype=Int64),
    ],
    source=transaction_source,
)
