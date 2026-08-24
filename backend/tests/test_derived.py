"""Phase 5 tests for app.features.derived."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.features import derived


def _df_with_indicators(rows: int = 20) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="1h", tz="UTC")
    close = np.linspace(1.0, 1.19, rows)
    return pd.DataFrame(
        {
            "close": close,
            "EMA20": close * 1.01,
            "EMA50": close * 1.02,
            "EMA200": close * 1.03,
            "BB_upper": close + 0.02,
            "BB_middle": close,
            "BB_lower": close - 0.02,
        },
        index=index,
    )


def test_ema_relationships_formula():
    df = _df_with_indicators(5)
    out = derived.add_ema_relationships(df)
    expected_20_50 = df["EMA20"] / df["EMA50"] - 1
    expected_50_200 = df["EMA50"] / df["EMA200"] - 1
    np.testing.assert_allclose(out["EMA20_to_EMA50"], expected_20_50)
    np.testing.assert_allclose(out["EMA50_to_EMA200"], expected_50_200)


def test_bollinger_derived_formula_and_bounds():
    df = _df_with_indicators(5)
    out = derived.add_bollinger_derived(df)
    # width should be constant here: (close+0.02 - (close-0.02)) / close = 0.04/close
    np.testing.assert_allclose(out["BB_width"], 0.04 / df["close"])
    # close == BB_middle -> position should be exactly 0.5 (midway between lower and upper)
    np.testing.assert_allclose(out["BB_position"], 0.5)


def test_historical_returns_match_pct_change_and_are_backward_looking():
    df = _df_with_indicators(20)
    out = derived.add_historical_returns(df, periods=(1, 3))
    np.testing.assert_allclose(out["return_1"].iloc[1:], df["close"].pct_change(1).iloc[1:])
    np.testing.assert_allclose(out["return_3"].iloc[3:], df["close"].pct_change(3).iloc[3:])
    # warmup rows must be NaN, not fabricated (e.g. via bfill)
    assert pd.isna(out["return_1"].iloc[0])
    assert out["return_3"].iloc[:3].isna().all()


def test_returns_no_lookahead_when_computed_on_truncated_series():
    full = _df_with_indicators(30)
    full_out = derived.add_historical_returns(full)
    truncated_out = derived.add_historical_returns(full.iloc[:20])
    for col in [f"return_{n}" for n in derived.DEFAULT_RETURN_PERIODS]:
        pd.testing.assert_series_equal(
            truncated_out[col], full_out[col].iloc[:20], check_names=False
        )


def test_add_all_derived_features_produces_expected_columns():
    df = _df_with_indicators(20)
    out = derived.add_all_derived_features(df)
    for col in derived.DERIVED_COLUMNS:
        assert col in out.columns
