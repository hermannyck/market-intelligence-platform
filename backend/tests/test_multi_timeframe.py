"""Phase 5 tests for app.features.multi_timeframe.

test_as_of_join_only_sees_bars_that_have_actually_closed is the critical one: it reproduces
the exact hazard described in the module docstring (an H4 bar labeled 00:00 spans 00:00-04:00
and must not be visible to an H1 row before 04:00, even though 00:00 < that H1 row's own
timestamp).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import Timeframe
from app.features import multi_timeframe as mtf


def test_compute_direction_bullish_bearish_and_warmup_nan():
    df = pd.DataFrame(
        {
            "EMA20": [1.10, 1.05, np.nan, 1.20],
            "EMA50": [1.05, 1.10, 1.00, 1.20],  # equal -> BEARISH per the > rule
        },
        index=pd.date_range("2024-01-01", periods=4, freq="1h", tz="UTC"),
    )
    direction = mtf.compute_direction(df)
    assert direction.iloc[0] == mtf.DIRECTION_BULLISH
    assert direction.iloc[1] == mtf.DIRECTION_BEARISH
    assert pd.isna(direction.iloc[2])  # EMA20 NaN -> can't determine
    assert direction.iloc[3] == mtf.DIRECTION_BEARISH  # equal counts as not-bullish


def test_as_of_join_only_sees_bars_that_have_actually_closed():
    # One H4 bar labeled 00:00 -> spans 00:00-04:00, closes at 04:00.
    h4_index = pd.DatetimeIndex(["2024-01-01 00:00"], tz="UTC")
    h4_direction = pd.Series([mtf.DIRECTION_BULLISH], index=h4_index)

    # H1 rows at 00:00, 01:00, 02:00, 03:00, 04:00 -> close at 01:00..05:00 respectively.
    h1_index = pd.date_range("2024-01-01 00:00", periods=5, freq="1h", tz="UTC")
    h1_close_time = pd.Series(h1_index + pd.Timedelta(hours=1), index=h1_index)

    result = mtf.as_of_join(h1_close_time, h4_direction, Timeframe.H4)

    # H1 rows closing at 01:00, 02:00, 03:00 are all BEFORE the H4 bar closes (04:00) --
    # the H4 bar must not be visible to them yet.
    assert pd.isna(result.iloc[0])  # H1 00:00 -> closes 01:00
    assert pd.isna(result.iloc[1])  # H1 01:00 -> closes 02:00
    assert pd.isna(result.iloc[2])  # H1 02:00 -> closes 03:00
    # H1 row at 03:00 closes exactly at 04:00 -- the same instant the H4 bar closes -> visible.
    assert result.iloc[3] == mtf.DIRECTION_BULLISH
    # H1 row at 04:00 closes at 05:00, well after the H4 bar closed -> still visible.
    assert result.iloc[4] == mtf.DIRECTION_BULLISH


def test_as_of_join_identity_for_own_timeframe():
    index = pd.date_range("2024-01-01", periods=5, freq="1h", tz="UTC")
    direction = pd.Series(
        [mtf.DIRECTION_BULLISH, mtf.DIRECTION_BEARISH, pd.NA, mtf.DIRECTION_BULLISH, mtf.DIRECTION_BEARISH],
        index=index,
    )
    close_time = pd.Series(index + pd.Timedelta(hours=1), index=index)
    result = mtf.as_of_join(close_time, direction, Timeframe.H1)
    for a, b in zip(result, direction):
        # `a == b` on two pd.NA values returns pd.NA, not True/False, and evaluating that in
        # a boolean `or` raises ("boolean value of NA is ambiguous") -- check isna() first
        # instead of relying on short-circuit truthiness of a possibly-NA comparison result.
        if pd.isna(a) or pd.isna(b):
            assert pd.isna(a) and pd.isna(b)
        else:
            assert a == b


def test_as_of_join_returns_nan_before_source_history_starts():
    # Source (e.g. M15) only starts well after the target's (e.g. D1) earliest rows.
    d1_index = pd.date_range("2020-01-01", periods=3, freq="1D", tz="UTC")
    d1_close_time = pd.Series(d1_index + pd.Timedelta(days=1), index=d1_index)

    m15_index = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    m15_direction = pd.Series([mtf.DIRECTION_BULLISH, mtf.DIRECTION_BEARISH], index=m15_index)

    result = mtf.as_of_join(d1_close_time, m15_direction, Timeframe.M15)
    assert result.isna().all()


def test_attach_multi_timeframe_bias_majority_vote_and_graceful_degradation():
    index = pd.date_range("2024-01-01", periods=1, freq="1h", tz="UTC")
    target_df = pd.DataFrame({"close": [1.1]}, index=index)

    def const_series(value, tf_index):
        return pd.Series([value], index=tf_index)

    # All four timeframes closed well before/at this single H1 row's own close time.
    m15_index = pd.DatetimeIndex(["2023-12-31 23:45"], tz="UTC")
    h1_index = pd.DatetimeIndex(["2024-01-01 00:00"], tz="UTC")
    h4_index = pd.DatetimeIndex(["2023-12-31 20:00"], tz="UTC")
    d1_index = pd.DatetimeIndex(["2023-12-31 00:00"], tz="UTC")

    # 3 BULLISH vs 1 BEARISH -> majority BULLISH.
    direction_by_tf = {
        Timeframe.M15: const_series(mtf.DIRECTION_BULLISH, m15_index),
        Timeframe.H1: const_series(mtf.DIRECTION_BULLISH, h1_index),
        Timeframe.H4: const_series(mtf.DIRECTION_BULLISH, h4_index),
        Timeframe.D1: const_series(mtf.DIRECTION_BEARISH, d1_index),
    }
    result = mtf.attach_multi_timeframe_bias(target_df, Timeframe.H1, direction_by_tf)
    assert result["mtf_bias"].iloc[0] == mtf.DIRECTION_BULLISH
    assert result["M15_direction"].iloc[0] == mtf.DIRECTION_BULLISH
    assert result["D1_direction"].iloc[0] == mtf.DIRECTION_BEARISH

    # 2 vs 2 tie -> MIXED.
    direction_by_tf[Timeframe.H4] = const_series(mtf.DIRECTION_BEARISH, h4_index)
    result = mtf.attach_multi_timeframe_bias(target_df, Timeframe.H1, direction_by_tf)
    assert result["mtf_bias"].iloc[0] == mtf.BIAS_MIXED

    # M15 unavailable (e.g. its history hasn't started yet) -> vote still resolves using the
    # remaining 3 timeframes instead of propagating NaN.
    direction_by_tf[Timeframe.M15] = pd.Series(
        [mtf.DIRECTION_BULLISH], index=pd.DatetimeIndex(["2030-01-01"], tz="UTC")
    )
    result = mtf.attach_multi_timeframe_bias(target_df, Timeframe.H1, direction_by_tf)
    assert pd.isna(result["M15_direction"].iloc[0])
    assert result["mtf_bias"].iloc[0] == mtf.DIRECTION_BEARISH  # H1 bull, H4 bear, D1 bear
