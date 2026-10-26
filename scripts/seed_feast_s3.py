"""Seed Feast offline parquet to S3 with interpretable fraud risk signals."""
import io
import os
from datetime import datetime, timedelta, timezone

import boto3
import numpy as np
import pandas as pd
from botocore.client import Config

# Must match feature_repo/features.py + docs/FEATURE_DICTIONARY.md
FEATURE_NAMES = [
    "geo_distance_from_last_txn",
    "spend_vs_median_ratio",
    "card_chip_present",
    "pin_authenticated",
    "ecommerce_channel",
    "known_merchant_repeat",
]


def build_demo_transactions(n_samples: int = 100, seed: int = 42) -> pd.DataFrame:
    """Synthetic but business-readable txn signals (km, spend ratio, 0/1 flags)."""
    rng = np.random.default_rng(seed)
    fraud = rng.random(n_samples) < 0.1
    geo = np.where(
        fraud,
        rng.uniform(200, 4000, n_samples),
        rng.exponential(12.0, n_samples).clip(0, 80),
    )
    spend = np.where(
        fraud,
        rng.uniform(4.0, 18.0, n_samples),
        rng.lognormal(mean=0.0, sigma=0.35, size=n_samples).clip(0.2, 3.5),
    )
    ecommerce = np.where(fraud, 1, (rng.random(n_samples) < 0.35).astype(int))
    chip = np.where(ecommerce == 1, 0, (rng.random(n_samples) < 0.85).astype(int))
    pin = np.where(
        (chip == 1) & (ecommerce == 0),
        (rng.random(n_samples) < 0.9).astype(int),
        0,
    )
    known = np.where(fraud, 0, (rng.random(n_samples) < 0.7).astype(int))
    return pd.DataFrame(
        {
            "geo_distance_from_last_txn": geo.astype("float32"),
            "spend_vs_median_ratio": spend.astype("float32"),
            "card_chip_present": chip.astype("int64"),
            "pin_authenticated": pin.astype("int64"),
            "ecommerce_channel": ecommerce.astype("int64"),
            "known_merchant_repeat": known.astype("int64"),
            "fraud": fraud.astype("int64"),
        }
    )


df = build_demo_transactions()
df["transaction_id"] = df.index.astype("int64")
now = datetime.now(timezone.utc)
df["event_timestamp"] = [now - timedelta(minutes=(len(df) - i)) for i in range(len(df))]
# Offline store schema = entity + features + timestamp (label kept for pipeline CSV seed only)
offline = df[
    ["transaction_id", "event_timestamp", *FEATURE_NAMES]
].copy()

endpoint = os.environ.get("AWS_ENDPOINT_URL") or os.environ["AWS_S3_ENDPOINT"]
bucket = os.environ["AWS_S3_BUCKET"]
key = (
    os.environ.get("FEAST_S3_PREFIX", "fd-gitops/features").strip("/")
    + "/transactions.parquet"
)

buf = io.BytesIO()
offline.to_parquet(buf, index=False)
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
print(
    f"Uploaded s3://{bucket}/{key} ({len(offline)} rows) cols={list(offline.columns)}"
)
print(
    "sample_means",
    {c: float(offline[c].mean()) for c in FEATURE_NAMES},
)
