"""Phase 9: market regime detection (spec Section 6) — one of five labels per bar, computed
using only trend strength, volatility, EMA relationships, and ATR available at that bar.

**Why rule-based, not clustering, for the live feature.** The spec says "consider an
unsupervised approach such as clustering if appropriate." A clustering model's centroids are
normally fit once on a dataset — but fitting on the *full* historical dataset (including bars
far in the future relative to some earlier row) and then using those centroids to label that
earlier row would leak future distributional information into a "historical" label, exactly
the kind of look-ahead bias this project is built to avoid. Making clustering properly causal
would require refitting per walk-forward window (expensive, and still an approximation of
"what a live model would have known"). Given that, the primary, live, per-bar `regime` feature
saved into `data/features/` uses a **deterministic rule** — trivially causal (every input is a
rolling/point-in-time calculation using only bars ≤ t), fully auditable, and reproducible
without any fitting step at all. `cluster_regimes_exploratory` below implements the clustering
alternative too, but explicitly as a non-causal, retrospective comparison tool only — see its
own docstring.

**The five labels are not on one axis.** Bullish/Bearish Trending and Sideways/Range-Bound
describe trend *direction and strength*; High/Low Volatility describe a different axis
entirely (how much the price is moving, regardless of direction). Spec Section 6 lists all
five as one set of regimes, so this module resolves them into a single categorical label with
an explicit priority: **volatility extremes are checked first**. An unusually volatile period
is arguably better described as "High Volatility" than shoehorned into a trend label that
implies more directional conviction than a whipsawing market actually has; only once
volatility is in its normal range does trend direction/strength decide the label.

    volatility_zscore[t] = rolling z-score of ATR14[t]/close[t] over the last
                            REGIME.volatility_lookback_bars bars (causal: the mean/std used
                            are computed only from bars up to and including t)
    trend_strength[t]    = (close[t] - close[t - trend_lookback]) / (ATR14[t] * sqrt(trend_lookback))
                            -- the price move over the lookback window, expressed in units of
                            "how many typical (ATR-sized) bar-moves was this", so it's
                            comparable across assets with very different price scales and
                            volatility levels

    if volatility_zscore[t] > REGIME.volatility_high_zscore:  HIGH_VOLATILITY
    elif volatility_zscore[t] < REGIME.volatility_low_zscore: LOW_VOLATILITY
    elif trend_strength[t] > REGIME.trend_strength_threshold
         and EMA20[t] > EMA50[t] > EMA200[t]:                 BULLISH_TRENDING
    elif trend_strength[t] < -REGIME.trend_strength_threshold
         and EMA20[t] < EMA50[t] < EMA200[t]:                 BEARISH_TRENDING
    else:                                                     SIDEWAYS_RANGE_BOUND

Warmup rows (not enough history for EMA200, ATR14, or either rolling window) are NaN, never
fabricated -- same convention as every prior phase.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import REGIME, RegimeLabel

REGIME_INPUT_COLUMNS = ("close", "ATR14", "EMA20", "EMA50", "EMA200")


def compute_atr_pct(df: pd.DataFrame) -> pd.Series:
    return df["ATR14"] / df["close"]


def compute_volatility_zscore(df: pd.DataFrame, lookback: int | None = None) -> pd.Series:
    lookback = REGIME.volatility_lookback_bars if lookback is None else lookback
    atr_pct = compute_atr_pct(df)
    rolling_mean = atr_pct.rolling(lookback).mean()
    rolling_std = atr_pct.rolling(lookback).std()
    return (atr_pct - rolling_mean) / rolling_std


def compute_trend_strength(df: pd.DataFrame, lookback: int | None = None) -> pd.Series:
    lookback = REGIME.trend_lookback_bars if lookback is None else lookback
    price_move = df["close"] - df["close"].shift(lookback)
    return price_move / (df["ATR14"] * np.sqrt(lookback))


def classify_regime(df: pd.DataFrame) -> pd.DataFrame:
    """Adds `volatility_zscore`, `trend_strength`, and `regime` columns. Requires the input to
    already have EMA20/EMA50/EMA200/ATR14/close (Phase 4's indicator output)."""
    missing = [c for c in REGIME_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"classify_regime requires columns {missing} (Phase 4 indicators).")

    df = df.copy()
    df["volatility_zscore"] = compute_volatility_zscore(df)
    df["trend_strength"] = compute_trend_strength(df)

    bullish_aligned = df["EMA20"] > df["EMA50"]
    bullish_aligned &= df["EMA50"] > df["EMA200"]
    bearish_aligned = df["EMA20"] < df["EMA50"]
    bearish_aligned &= df["EMA50"] < df["EMA200"]

    has_inputs = df["volatility_zscore"].notna() & df["trend_strength"].notna()

    regime = pd.Series(pd.NA, index=df.index, dtype="object")
    high_vol = has_inputs & (df["volatility_zscore"] > REGIME.volatility_high_zscore)
    low_vol = has_inputs & ~high_vol & (df["volatility_zscore"] < REGIME.volatility_low_zscore)
    normal_vol = has_inputs & ~high_vol & ~low_vol
    bullish = normal_vol & (df["trend_strength"] > REGIME.trend_strength_threshold) & bullish_aligned
    bearish = normal_vol & (df["trend_strength"] < -REGIME.trend_strength_threshold) & bearish_aligned
    sideways = normal_vol & ~bullish & ~bearish

    regime.loc[high_vol] = RegimeLabel.HIGH_VOLATILITY.value
    regime.loc[low_vol] = RegimeLabel.LOW_VOLATILITY.value
    regime.loc[bullish] = RegimeLabel.BULLISH_TRENDING.value
    regime.loc[bearish] = RegimeLabel.BEARISH_TRENDING.value
    regime.loc[sideways] = RegimeLabel.SIDEWAYS.value

    df["regime"] = regime
    return df


def regime_distribution(df: pd.DataFrame, regime_col: str = "regime") -> dict:
    """Counts/percentages per label among rows that have one -- feeds the dashboard's
    "Regime Distribution" panel (spec Section 6) directly."""
    labeled = df[regime_col].dropna()
    total = len(labeled)
    counts = {k: int(v) for k, v in labeled.value_counts().items()}
    percentages = {k: round(v / total * 100, 2) for k, v in counts.items()} if total else {}
    return {"total_labeled_rows": total, "counts": counts, "percentages": percentages}


def cluster_regimes_exploratory(df: pd.DataFrame, n_clusters: int = 5, random_state: int = 42) -> pd.Series:
    """Unsupervised (KMeans) alternative, per spec Section 6's "consider ... clustering if
    appropriate" -- **exploratory/retrospective only, not causal, never saved as a live
    feature or used by any model.** KMeans centroids here are fit once on the *entire* input
    (including bars that are "in the future" relative to any earlier row being labeled), which
    is exactly the kind of look-ahead this project avoids for anything that actually feeds a
    model. This function exists purely so the clustering approach can be inspected and
    compared against the rule-based `regime` column in a notebook -- see
    `notebooks/phase9_regime_detection_eda.ipynb`.

    Returns raw integer cluster ids (0..n_clusters-1) with no attempt to map them to
    BULLISH_TRENDING/etc. labels -- that mapping is subjective and left to visual/statistical
    inspection in the notebook, not hardcoded here.
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    feature_cols = ["trend_strength", "volatility_zscore", "EMA20_to_EMA50", "EMA50_to_EMA200"]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"cluster_regimes_exploratory requires columns {missing}.")

    valid = df.dropna(subset=feature_cols)
    if len(valid) < n_clusters:
        return pd.Series(pd.NA, index=df.index, dtype="object")

    X = StandardScaler().fit_transform(valid[feature_cols])
    labels = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10).fit_predict(X)

    result = pd.Series(pd.NA, index=df.index, dtype="object")
    result.loc[valid.index] = labels
    return result
