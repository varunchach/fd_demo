"""Generate a small synthetic transaction dataset for the Feast demo feature repo.
Mirrors the feature semantics used by the official RHOAI fraud-detection tutorial:
distance from the previous transaction, ratio to median purchase price, and
whether a chip was used.
"""
import os
import random
from datetime import datetime, timedelta, timezone

import pandas as pd

os.makedirs("data", exist_ok=True)

random.seed(42)
n = 200
now = datetime.now(timezone.utc)

rows = []
for i in range(n):
    rows.append(
        {
            "transaction_id": i,
            "event_timestamp": now - timedelta(minutes=(n - i)),
            "distance_from_last_transaction": round(random.uniform(0, 150), 2),
            "ratio_to_median_purchase_price": round(random.uniform(0.1, 5.0), 2),
            "used_chip": random.choice([0, 1]),
        }
    )

df = pd.DataFrame(rows)
df.to_parquet("data/transactions.parquet", index=False)
print(f"Wrote {len(df)} rows to data/transactions.parquet")
