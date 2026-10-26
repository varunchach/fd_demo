"""Apply FeatureService from repo and create a SavedDataset for the Datasets UI."""
import io
import os
from pathlib import Path

import boto3
import pandas as pd
from botocore.client import Config
from feast import FeatureStore
from feast.infra.offline_stores.file_source import SavedDatasetFileStorage

FEATURE_VIEW = "fraud_txn_risk_signals"
FEATURE_REFS = [
    f"{FEATURE_VIEW}:geo_distance_from_last_txn",
    f"{FEATURE_VIEW}:spend_vs_median_ratio",
    f"{FEATURE_VIEW}:card_chip_present",
    f"{FEATURE_VIEW}:pin_authenticated",
    f"{FEATURE_VIEW}:ecommerce_channel",
    f"{FEATURE_VIEW}:known_merchant_repeat",
]

REPO = Path("/feast-data/fraud_detection/feature_repo")
store = FeatureStore(repo_path=str(REPO))
store.apply([])
print("feature_services", [fs.name for fs in store.list_feature_services()])
print("feature_views", [fv.name for fv in store.list_feature_views()])

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
df = pd.read_parquet(io.BytesIO(client.get_object(Bucket=bucket, Key=key)["Body"].read()))
if df["event_timestamp"].dt.tz is None:
    df["event_timestamp"] = df["event_timestamp"].dt.tz_localize("UTC")

store.write_to_online_store(FEATURE_VIEW, df)
print("online_write_rows", len(df))

entity_df = df[["transaction_id", "event_timestamp"]].copy()
job = store.get_historical_features(
    entity_df=entity_df,
    features=FEATURE_REFS,
)

out_dir = REPO / "data"
out_dir.mkdir(parents=True, exist_ok=True)
storage = SavedDatasetFileStorage(path=str(out_dir / "fraud_training_dataset.parquet"))
dataset = store.create_saved_dataset(
    from_=job,
    name="fraud_training_dataset",
    storage=storage,
    tags={"purpose": "demo-training"},
    allow_overwrite=True,
)
print("saved_dataset", dataset.name)
print("datasets", [d.name for d in store.list_saved_datasets()])
