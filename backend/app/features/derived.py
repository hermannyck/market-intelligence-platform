"""Phase 5: derived/relationship features built on top of Phase 4's raw indicator columns
(spec Section 4). Every value here is a function of the current row and past rows only --
ratios of already-computed (already-verified no-lookahead) indicator columns, and
backward-looking historical returns via `pct_change`, which by definition only divides by an
earlier value.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_RETURN_PERIODS: tuple[int, ...] = (1, 3, 6, 12)


def add_ema_relationships(df: pd.DataFrame) -> pd.DataFrame:
    """EMA20_to_EMA50 / EMA50_to_EMA200: relative difference between adjacent EMAs, e.g.
    EMA20_to_EMA50 = EMA20/EMA50 - 1. Scale-invariant (works the same for EUR/USD ~1.1,
    BTC/USD ~77000, and XAU/USD ~4700), and centered at 0 (positive = faster EMA above
    slower EMA = short-term uptrend relative to the longer one)."""
    df = df.copy()
    df["EMA20_to_EMA50"] = df["EMA20"] / df["EMA50"] - 1
    df["EMA50_to_EMA200"] = df["EMA50"] / df["EMA200"] - 1
    return df


def add_bollinger_derived(df: pd.DataFrame) -> pd.DataFrame:
    """BB_width (normalized band width) and BB_position (%B -- where close sits within the
    bands; 0 = at the lower band, 1 = at the upper band, can go outside [0, 1] on a breakout)."""
    df = df.copy()
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_middle"]
    df["BB_position"] = (df["close"] - df["BB_lower"]) / (df["BB_upper"] - df["BB_lower"])
    return df


def add_historical_returns(df: pd.DataFrame, periods: tuple[int, ...] = DEFAULT_RETURN_PERIODS) -> pd.DataFrame:
    """N-period historical return: close[t] / close[t-N] - 1, for each N in `periods`.
    Purely backward-looking by construction (pandas `pct_change` divides by an earlier row)."""
    df = df.copy()
    for n in periods:
        df[f"return_{n}"] = df["close"].pct_change(n)
    return df


def add_all_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    df = add_ema_relationships(df)
    df = add_bollinger_derived(df)
    df = add_historical_returns(df)
    return df


DERIVED_COLUMNS = (
    ["EMA20_to_EMA50", "EMA50_to_EMA200", "BB_width", "BB_position"]
    + [f"return_{n}" for n in DEFAULT_RETURN_PERIODS]
)
