"""Write Feast offline parquet into the ONLINE store (run inside Feast online pod)."""
import io
import os

import boto3
import pandas as pd
from botocore.client import Config
from feast import FeatureStore

FEATURE_VIEW = "fraud_txn_risk_signals"
SAMPLE_FEATURES = [
    f"{FEATURE_VIEW}:card_chip_present",
    f"{FEATURE_VIEW}:ecommerce_channel",
]

ep = os.environ.get("AWS_ENDPOINT_URL") or os.environ["AWS_S3_ENDPOINT"]
bucket = os.environ["AWS_S3_BUCKET"]
key = (
    os.environ.get("FEAST_S3_PREFIX", "fd-gitops/features").strip("/")
    + "/transactions.parquet"
)
client = boto3.client(
    "s3",
    endpoint_url=ep,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    config=Config(s3={"addressing_style": "path"}),
)
obj = client.get_object(Bucket=bucket, Key=key)
df = pd.read_parquet(io.BytesIO(obj["Body"].read()))
print("loaded_rows", len(df), "cols", list(df.columns))
if df["event_timestamp"].dt.tz is None:
    df["event_timestamp"] = df["event_timestamp"].dt.tz_localize("UTC")

repo = os.environ.get("FEAST_REPO", "/feast-data/fd_gitops/feature_repo")
store = FeatureStore(repo)
store.write_to_online_store(FEATURE_VIEW, df)
print("write_to_online_store=OK view=", FEATURE_VIEW)
feats = store.get_online_features(
    features=SAMPLE_FEATURES,
    entity_rows=[{"transaction_id": 0}, {"transaction_id": 1}],
).to_dict()
print("sample", feats)
