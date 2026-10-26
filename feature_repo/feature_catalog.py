"""Single source of truth for fraud Feature Store names (UI + pipeline + seed).

Keep names short, domain-specific, and self-explanatory so the RHOAI Feature Store
UI reads as a credit/card fraud scorecard — not Feast's driver_hourly_stats demo.
"""
from __future__ import annotations

from typing import Final

# Feast object names (what clients see under Feature Store)
ENTITY: Final = "transaction_id"
FEATURE_VIEW: Final = "fraud_txn_risk_signals"
FEATURE_SERVICE: Final = "fraud_scoring_service"

# Online / historical feature refs: "<view>:<feature>"
FEATURE_NAMES: Final[list[str]] = [
    "geo_distance_from_last_txn",  # km from previous txn
    "spend_vs_median_ratio",  # amount / customer median spend
    "card_chip_present",  # 1 = EMV chip at POS
    "pin_authenticated",  # 1 = PIN verified
    "ecommerce_channel",  # 1 = online / CNP
    "known_merchant_repeat",  # 1 = merchant seen before
]

FEATURE_REFS: Final[list[str]] = [f"{FEATURE_VIEW}:{n}" for n in FEATURE_NAMES]

# Business ranges for docs / UI tooltips
FEATURE_META: Final[dict[str, dict[str, str]]] = {
    "geo_distance_from_last_txn": {
        "unit": "km",
        "typical": "0–50 local; >500 = geo jump",
        "risk_signal": "Large jump → possible stolen-card use elsewhere",
    },
    "spend_vs_median_ratio": {
        "unit": "ratio",
        "typical": "0.5–2.0 normal; >5 unusual",
        "risk_signal": "Spike vs median → burst / ticket-size fraud",
    },
    "card_chip_present": {
        "unit": "0/1",
        "typical": "1 card-present EMV; 0 magstripe/CNP",
        "risk_signal": "Chip present lowers skimming risk",
    },
    "pin_authenticated": {
        "unit": "0/1",
        "typical": "1 PIN OK; 0 no PIN",
        "risk_signal": "PIN success supports legitimate cardholder",
    },
    "ecommerce_channel": {
        "unit": "0/1",
        "typical": "1 online; 0 in-store",
        "risk_signal": "Online raises card-not-present exposure",
    },
    "known_merchant_repeat": {
        "unit": "0/1",
        "typical": "1 seen before; 0 first-time merchant",
        "risk_signal": "New merchants add unfamiliarity risk",
    },
}


def build_demo_transactions(n_samples: int = 100, seed: int = 42):
    """Synthetic but *interpretable* txn risk signals (not random Gaussian blobs)."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    # ~10% fraud-like: large geo jump + high spend + online + new merchant
    fraud = rng.random(n_samples) < 0.1

    geo = np.where(
        fraud,
        rng.uniform(200, 4000, n_samples),  # interstate / cross-border jump
        rng.exponential(12.0, n_samples).clip(0, 80),  # local commute radius
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

    df = pd.DataFrame(
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
    return df
