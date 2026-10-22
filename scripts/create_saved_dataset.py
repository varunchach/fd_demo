"""Create SavedDataset using a local parquet FileSource (avoids s3fs)."""
import io
import os
import shutil
from pathlib import Path

import boto3
import pandas as pd
from botocore.client import Config
from feast import FeatureStore

REPO = Path("/feast-data/fraud_detection/feature_repo")
DATA = REPO / "data"
DATA.mkdir(parents=True, exist_ok=True)
LOCAL_PARQUET = DATA / "transactions.parquet"

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
df.to_parquet(LOCAL_PARQUET, index=False)

# Point FileSource at local file for historical retrieval / saved dataset
features_py = (REPO / "features.py").read_text()
patched = features_py
# Force local path regardless of env-built s3 path
import re

patched = re.sub(
    r'path=f?"?s3://[^"]+"?',
    f'path="{LOCAL_PARQUET.as_posix()}"',
    patched,
    count=1,
)
if f'path="{LOCAL_PARQUET.as_posix()}"' not in patched:
    # fallback: replace path= line inside FileSource
    patched = re.sub(
        r"path=.*,",
        f'path="{LOCAL_PARQUET.as_posix()}",',
        patched,
        count=1,
    )
(REPO / "features.py").write_text(patched)

store = FeatureStore(repo_path=str(REPO))
store.apply([])
store.write_to_online_store("fraud_features", df)

entity_df = df[["transaction_id", "event_timestamp"]].copy()
job = store.get_historical_features(
    entity_df=entity_df,
    features=[
        "fraud_features:distance_from_last_transaction",
        "fraud_features:ratio_to_median_purchase_price",
        "fraud_features:used_chip",
        "fraud_features:used_pin_number",
        "fraud_features:online_order",
        "fraud_features:repeat_retailer",
    ],
)

from feast.infra.offline_stores.file_source import SavedDatasetFileStorage

out = DATA / "fraud_training_dataset.parquet"
dataset = store.create_saved_dataset(
    from_=job,
    name="fraud_training_dataset",
    storage=SavedDatasetFileStorage(path=str(out)),
    tags={"purpose": "demo-training"},
    feature_service_name="fraud_txn_service",
    allow_overwrite=True,
)
print("feature_services", [fs.name for fs in store.list_feature_services()])
print("saved_dataset", dataset.name)
print("datasets", [d.name for d in store.list_saved_datasets()])
