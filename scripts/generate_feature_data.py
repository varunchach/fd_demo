"""Generate the canonical fraud-transaction dataset for the Feature Store.
Uses the exact same generation parameters as notebook/fraud_detection.ipynb
and pipeline/pipeline.py (same random_state), so the feature store's data
matches what the notebook/pipeline would otherwise generate ad hoc.
"""
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
from sklearn.datasets import make_classification

FEATURE_NAMES = [
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "used_chip",
    "used_pin_number",
    "online_order",
    "repeat_retailer",
]

os.makedirs("data", exist_ok=True)

X, y = make_classification(
    n_samples=5000,
    n_features=len(FEATURE_NAMES),
    n_informative=4,
    n_redundant=0,
    weights=[0.97, 0.03],
    class_sep=1.2,
    random_state=42,
)

df = pd.DataFrame(X, columns=FEATURE_NAMES)
df["fraud"] = y
df["transaction_id"] = df.index

now = datetime.now(timezone.utc)
df["event_timestamp"] = [now - timedelta(minutes=(len(df) - i)) for i in range(len(df))]

df.to_parquet("data/transactions.parquet", index=False)
print(f"Wrote {len(df)} rows to data/transactions.parquet")
