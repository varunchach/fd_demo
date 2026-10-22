import io
import os

import boto3
import pandas as pd
from botocore.client import Config
from feast import FeatureStore

ep = os.environ["AWS_S3_ENDPOINT"]
bucket = os.environ["AWS_S3_BUCKET"]
key = (
    os.environ.get("FEAST_S3_PREFIX", "fraud-detection/features").strip("/")
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

store = FeatureStore("/feast-data/fraud_detection/feature_repo")
store.write_to_online_store("fraud_features", df)
print("write_to_online_store=OK")
feats = store.get_online_features(
    features=["fraud_features:used_chip", "fraud_features:online_order"],
    entity_rows=[{"transaction_id": 0}, {"transaction_id": 1}],
).to_dict()
print("sample", feats)
