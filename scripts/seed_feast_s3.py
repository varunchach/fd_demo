"""Seed Feast offline parquet to S3 (GitOps PostSync hook)."""
import io
import os
from datetime import datetime, timedelta, timezone

import boto3
import pandas as pd
from botocore.client import Config
from sklearn.datasets import make_classification

names = [
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "used_chip",
    "used_pin_number",
    "online_order",
    "repeat_retailer",
]
X, _ = make_classification(
    n_samples=100,
    n_features=6,
    n_informative=4,
    n_redundant=0,
    weights=[0.9, 0.1],
    class_sep=1.2,
    random_state=42,
)
df = pd.DataFrame(X, columns=names)
df["transaction_id"] = df.index.astype("int64")
now = datetime.now(timezone.utc)
df["event_timestamp"] = [now - timedelta(minutes=(len(df) - i)) for i in range(len(df))]

endpoint = os.environ.get("AWS_ENDPOINT_URL") or os.environ["AWS_S3_ENDPOINT"]
bucket = os.environ["AWS_S3_BUCKET"]
key = (
    os.environ.get("FEAST_S3_PREFIX", "fd-gitops/features").strip("/")
    + "/transactions.parquet"
)

buf = io.BytesIO()
df.to_parquet(buf, index=False)
buf.seek(0)

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    config=Config(s3={"addressing_style": "path"}),
)
try:
    client.head_bucket(Bucket=bucket)
except Exception:
    client.create_bucket(Bucket=bucket)
client.put_object(Bucket=bucket, Key=key, Body=buf.getvalue())
print(f"Uploaded s3://{bucket}/{key} ({len(df)} rows)")
