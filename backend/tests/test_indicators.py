"""Phase 4 tests for app.features.indicators.

The most important test in this file is the "no lookahead" one: it proves indicator values
computed on a truncated series exactly match those computed on the full series, for every row
within the truncated range. That's the concrete, falsifiable version of "these indicators
only use information available at the time" -- not just an assumption from the formulas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.features import indicators


def _synthetic_ohlcv(rows: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="1h", tz="UTC")
    close = 1.10 + np.cumsum(rng.normal(0, 0.0005, rows))
    high = close + rng.uniform(0.0001, 0.0015, rows)
    low = close - rng.uniform(0.0001, 0.0015, rows)
    open_ = close + rng.normal(0, 0.0003, rows)
    volume = rng.integers(100, 1000, rows).astype(float)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )
    df.index.name = "timestamp"
    return df


def test_add_all_indicators_produces_expected_columns():
    df = indicators.add_all_indicators(_synthetic_ohlcv())
    for col in indicators.INDICATOR_COLUMNS:
        assert col in df.columns, f"missing expected column {col}"


def test_missing_ohlcv_columns_raises():
    df = _synthetic_ohlcv().drop(columns=["volume"])
    with pytest.raises(ValueError, match="missing required OHLCV"):
        indicators.add_all_indicators(df)


def test_non_monotonic_index_raises():
    df = _synthetic_ohlcv().iloc[::-1]  # reverse -> descending, not sorted ascending
    with pytest.raises(ValueError, match="sorted ascending"):
        indicators.add_all_indicators(df)


def test_indicator_value_ranges_are_sane():
    df = indicators.add_all_indicators(_synthetic_ohlcv())
    valid = df.dropna(subset=indicators.INDICATOR_COLUMNS)
    assert len(valid) > 0

    assert (valid["RSI14"].between(0, 100)).all()
    assert (valid["ATR14"] >= 0).all()
    assert (valid["BB_lower"] <= valid["BB_middle"]).all()
    assert (valid["BB_middle"] <= valid["BB_upper"]).all()
    # MACD histogram should equal MACD line minus signal line, by definition.
    np.testing.assert_allclose(
        valid["MACD_histogram"], valid["MACD"] - valid["MACD_signal"], atol=1e-8
    )


def test_warmup_period_is_nan_not_fabricated():
    df = indicators.add_all_indicators(_synthetic_ohlcv())
    # EMA200 needs 200 bars of history -- the first row can't possibly have a valid value.
    assert pd.isna(df["EMA200"].iloc[0])
    # ...but by the end of a 300-row series there's been plenty of history.
    assert pd.notna(df["EMA200"].iloc[-1])


@pytest.mark.parametrize("truncate_at", [220, 260])
def test_no_lookahead_indicators_match_when_computed_on_truncated_series(truncate_at):
    full = _synthetic_ohlcv(rows=300)
    full_result = indicators.add_all_indicators(full)

    truncated = full.iloc[:truncate_at].copy()
    truncated_result = indicators.add_all_indicators(truncated)

    # Every row that exists in the truncated run must have an identical indicator value to
    # the same row computed with the full series available -- i.e. rows after the cutoff
    # cannot have influenced rows before it.
    for col in indicators.INDICATOR_COLUMNS:
        pd.testing.assert_series_equal(
            truncated_result[col],
            full_result[col].iloc[:truncate_at],
            check_names=False,
        )
