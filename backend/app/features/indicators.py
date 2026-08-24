"""Phase 4: the five spec-mandated technical indicators (EMA, RSI, MACD, ATR, Bollinger
Bands), computed via ``pandas-ta`` on top of Phase 3's cleaned ``data/processed/`` output.

**No lookahead by construction.** All five are standard trailing/causal TA formulas — EMA
(exponential smoothing over past bars), Wilder's RSI/ATR smoothing, MACD (a difference of two
EMAs plus a signal EMA), and Bollinger Bands (a rolling mean/std) — none use centered windows
or future bars. This is verified, not just assumed: see
``tests/test_indicators.py::test_no_lookahead_*``, which recomputes indicators on a truncated
series and asserts every value up to the truncation point is bit-identical to the value
computed on the full series.

**Warmup NaNs are left in place, not filled or dropped.** A row before an indicator's warmup
period has elapsed (e.g. the first 199 rows have no EMA200) genuinely has no valid value yet —
backfilling or interpolating it would fabricate information. Phase 5/6 decide how to handle
these NaNs when assembling the final training feature set (typically: drop rows before the
longest-warmup indicator is available).

Only the five indicators themselves are computed here, at exactly the parameters in
``app.config.INDICATORS``. Derived/relationship features (EMA20_to_EMA50, BB_width,
BB_position, returns, etc. — spec Section 4) are Phase 5's job, built on top of this module's
output.
"""
from __future__ import annotations

import pandas as pd
import pandas_ta as ta  # noqa: F401 - registers the `.ta` accessor used below

from app.config import INDICATORS

REQUIRED_INPUT_COLUMNS = ("open", "high", "low", "close", "volume")


def _require_ohlcv(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Input is missing required OHLCV columns: {missing}")


def add_ema(df: pd.DataFrame) -> pd.DataFrame:
    """EMA 20 / 50 / 200 (app.config.INDICATORS.ema_periods)."""
    df = df.copy()
    for period in INDICATORS.ema_periods:
        df[f"EMA{period}"] = df.ta.ema(length=period)
    return df


def add_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """RSI 14 (app.config.INDICATORS.rsi_period)."""
    df = df.copy()
    df[f"RSI{INDICATORS.rsi_period}"] = df.ta.rsi(length=INDICATORS.rsi_period)
    return df


def add_macd(df: pd.DataFrame) -> pd.DataFrame:
    """MACD line / signal line / histogram (standard 12/26/9)."""
    df = df.copy()
    macd = df.ta.macd(
        fast=INDICATORS.macd_fast, slow=INDICATORS.macd_slow, signal=INDICATORS.macd_signal
    )
    # Column names carry a version-specific numeric suffix (e.g. "MACD_12_26_9") -- match by
    # prefix instead of hardcoding the exact suffix, so a pandas-ta formatting change doesn't
    # silently produce a KeyError or, worse, a silently-empty column.
    df["MACD"] = macd[[c for c in macd.columns if c.startswith("MACD_")][0]]
    df["MACD_signal"] = macd[[c for c in macd.columns if c.startswith("MACDs_")][0]]
    df["MACD_histogram"] = macd[[c for c in macd.columns if c.startswith("MACDh_")][0]]
    return df


def add_atr(df: pd.DataFrame) -> pd.DataFrame:
    """ATR 14 (app.config.INDICATORS.atr_period), Wilder's smoothing (pandas-ta default)."""
    df = df.copy()
    df[f"ATR{INDICATORS.atr_period}"] = df.ta.atr(length=INDICATORS.atr_period)
    return df


def add_bollinger_bands(df: pd.DataFrame) -> pd.DataFrame:
    """Bollinger Bands: period 20, 2 standard deviations (app.config.INDICATORS)."""
    df = df.copy()
    bb = df.ta.bbands(length=INDICATORS.bb_period, std=INDICATORS.bb_std_dev)
    # pandas-ta always returns lower/mid/upper as the first three columns, in that order --
    # matching by position (rather than the std-dev suffix, which this fork renders as
    # "20_2.0_2.0") is the robust choice here.
    df["BB_lower"] = bb.iloc[:, 0]
    df["BB_middle"] = bb.iloc[:, 1]
    df["BB_upper"] = bb.iloc[:, 2]
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Apply all five indicators. Input must already be sorted ascending by timestamp (Phase 3
    output is) -- pandas-ta's rolling/EWM calculations assume row order == time order."""
    _require_ohlcv(df)
    if not df.index.is_monotonic_increasing:
        raise ValueError("Input must be sorted ascending by timestamp before computing indicators.")
    df = add_ema(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_atr(df)
    df = add_bollinger_bands(df)
    return df


INDICATOR_COLUMNS = (
    [f"EMA{p}" for p in INDICATORS.ema_periods]
    + [f"RSI{INDICATORS.rsi_period}"]
    + ["MACD", "MACD_signal", "MACD_histogram"]
    + [f"ATR{INDICATORS.atr_period}"]
    + ["BB_lower", "BB_middle", "BB_upper"]
)
