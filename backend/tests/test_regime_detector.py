"""Phase 9 tests for app.regime.detector.

Each regime-label test builds a long, slightly-noisy "baseline" series (so the rolling
volatility mean/std are well-defined and non-degenerate) and then perturbs only the LAST row
to deterministically push it into one specific regime, leaving every earlier row's rolling
window untouched by the perturbation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import REGIME, RegimeLabel
from app.regime import detector


def _baseline_df(n: int = 130, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.01, n))  # gentle random walk, no real trend
    atr = 1.0 + rng.normal(0, 0.02, n)  # small noise around a stable baseline ATR
    df = pd.DataFrame(
        {
            "close": close,
            "ATR14": atr,
            "EMA20": close,   # flat/equal EMAs -> no directional alignment by default
            "EMA50": close,
            "EMA200": close,
        },
        index=index,
    )
    return df


def _pin_last_row_to_normal_volatility(df: pd.DataFrame) -> None:
    """Volatility is atr_pct = ATR14/close, so changing `close` (as every trend-focused test
    below does, to control trend_strength) shifts atr_pct too, even with ATR14 unchanged --
    and the baseline's own last-row atr_pct is additionally a random draw that can occasionally
    land outside the +-1 z-score band by chance (ordinary sampling noise in a 100-sample
    window). Call this AFTER setting the row's final `close` value: it sets ATR14 so that
    atr_pct lands exactly at the preceding window's mean, guaranteeing a near-zero z-score
    regardless of what close ended up being."""
    lookback = REGIME.volatility_lookback_bars
    atr_pct = df["ATR14"] / df["close"]
    preceding_mean_atr_pct = atr_pct.iloc[-1 - lookback : -1].mean()
    last_close = df["close"].iloc[-1]
    df.iloc[-1, df.columns.get_loc("ATR14")] = preceding_mean_atr_pct * last_close


def test_compute_atr_pct():
    df = pd.DataFrame({"close": [100.0, 200.0], "ATR14": [1.0, 4.0]})
    result = detector.compute_atr_pct(df)
    np.testing.assert_allclose(result, [0.01, 0.02])


def test_classify_regime_requires_indicator_columns():
    df = pd.DataFrame({"close": [1.0, 2.0]})
    with pytest.raises(ValueError, match="requires columns"):
        detector.classify_regime(df)


def test_classify_regime_warmup_is_nan():
    df = _baseline_df(n=130)
    out = detector.classify_regime(df)
    # Row 0 can't have a 100-bar volatility lookback yet.
    assert pd.isna(out["regime"].iloc[0])
    assert pd.isna(out["volatility_zscore"].iloc[0])


def test_high_volatility_label():
    df = _baseline_df(n=130)
    df.iloc[-1, df.columns.get_loc("ATR14")] = 5.0  # far above the ~1.0 baseline -> high z-score
    out = detector.classify_regime(df)
    assert out["regime"].iloc[-1] == RegimeLabel.HIGH_VOLATILITY.value


def test_low_volatility_label():
    df = _baseline_df(n=130)
    df.iloc[-1, df.columns.get_loc("ATR14")] = 0.1  # far below baseline -> low (negative) z-score
    out = detector.classify_regime(df)
    assert out["regime"].iloc[-1] == RegimeLabel.LOW_VOLATILITY.value


def test_bullish_trending_label():
    df = _baseline_df(n=130)
    last = df.index[-1]
    lookback = REGIME.trend_lookback_bars
    close_before = df["close"].iloc[-1 - lookback]
    # Strong upward move over the lookback window, bullish EMA alignment.
    df.loc[last, "close"] = close_before + 50 * df["ATR14"].iloc[-1]
    df.loc[last, ["EMA20", "EMA50", "EMA200"]] = [3, 2, 1]  # EMA20 > EMA50 > EMA200
    _pin_last_row_to_normal_volatility(df)  # after the close change, so atr_pct stays baseline
    out = detector.classify_regime(df)
    assert out["regime"].iloc[-1] == RegimeLabel.BULLISH_TRENDING.value


def test_bearish_trending_label():
    df = _baseline_df(n=130)
    last = df.index[-1]
    lookback = REGIME.trend_lookback_bars
    close_before = df["close"].iloc[-1 - lookback]
    df.loc[last, "close"] = close_before - 50 * df["ATR14"].iloc[-1]
    df.loc[last, ["EMA20", "EMA50", "EMA200"]] = [1, 2, 3]  # EMA20 < EMA50 < EMA200
    _pin_last_row_to_normal_volatility(df)
    out = detector.classify_regime(df)
    assert out["regime"].iloc[-1] == RegimeLabel.BEARISH_TRENDING.value


def test_sideways_label_when_trend_weak_despite_normal_volatility():
    df = _baseline_df(n=130)
    _pin_last_row_to_normal_volatility(df)
    # Baseline is already a flat random walk with flat/equal EMAs -> weak trend, normal vol.
    out = detector.classify_regime(df)
    assert out["regime"].iloc[-1] == RegimeLabel.SIDEWAYS.value


def test_sideways_when_trend_strong_but_emas_not_aligned():
    df = _baseline_df(n=130)
    last = df.index[-1]
    lookback = REGIME.trend_lookback_bars
    close_before = df["close"].iloc[-1 - lookback]
    df.loc[last, "close"] = close_before + 50 * df["ATR14"].iloc[-1]  # strong up move...
    df.loc[last, ["EMA20", "EMA50", "EMA200"]] = [1, 3, 2]  # ...but EMAs not bullishly aligned
    _pin_last_row_to_normal_volatility(df)
    out = detector.classify_regime(df)
    assert out["regime"].iloc[-1] == RegimeLabel.SIDEWAYS.value


def test_no_lookahead_regime_matches_when_computed_on_truncated_series():
    full = _baseline_df(n=200)
    full_out = detector.classify_regime(full)
    truncated_out = detector.classify_regime(full.iloc[:150])
    for col in ("volatility_zscore", "trend_strength", "regime"):
        pd.testing.assert_series_equal(
            truncated_out[col], full_out[col].iloc[:150], check_names=False
        )


def test_regime_distribution_counts_and_percentages():
    df = pd.DataFrame({"regime": ["Bullish Trending", "Bullish Trending", "Sideways / Range-Bound", None]})
    dist = detector.regime_distribution(df)
    assert dist["total_labeled_rows"] == 3
    assert dist["counts"]["Bullish Trending"] == 2
    assert dist["percentages"]["Bullish Trending"] == pytest.approx(66.67, abs=0.01)


def test_cluster_regimes_exploratory_smoke():
    df = _baseline_df(n=200)
    df = detector.classify_regime(df)
    df["EMA20_to_EMA50"] = 0.0
    df["EMA50_to_EMA200"] = 0.0
    clusters = detector.cluster_regimes_exploratory(df, n_clusters=3)
    valid = clusters.dropna()
    assert len(valid) > 0
    assert set(valid.unique()) <= {0, 1, 2}


def test_cluster_regimes_exploratory_missing_columns_raises():
    df = pd.DataFrame({"trend_strength": [1.0]})
    with pytest.raises(ValueError, match="requires columns"):
        detector.cluster_regimes_exploratory(df)
