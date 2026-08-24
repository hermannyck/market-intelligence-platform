"""Phase 5: multi-timeframe alignment without look-ahead (spec Section 2).

**The core hazard:** a bar's timestamp is its OPEN time (standard OHLC convention — Phase 2/3
never changed this). A bar is only "available" — fully observed, safe to use as a feature —
at its CLOSE time (open + ``app.config.BAR_DURATION[timeframe]``). Naively joining timeframes
on their raw timestamp index would let, say, an H4 bar labeled 00:00 (which actually spans
00:00-04:00 and doesn't close until 04:00) leak into an H1 row at 01:00 — four hours before
that H4 bar actually finished forming. Every lookup in this module joins on **close time**,
using a backward as-of match, specifically to rule that out.

**Symmetric across coarser and finer timeframes.** The spec's example asks for M15, H1, H4,
and D1 direction *together* when generating an H1 prediction — including M15, which is finer
than H1, not just the coarser H4/D1. The as-of-by-close-time join handles this uniformly: for
any target row, "the most recently closed bar in timeframe Y" is well-defined whether Y is
coarser or finer than the target's own timeframe. A target row includes its own timeframe's
direction too (the join against its own series is just an identity match).

**Honest degradation when a timeframe has no data yet.** M15 history only goes back ~60-90
days (see docs/data_sources.md); for H1/H4/D1 rows before that window, there is no M15 bar to
look up at all, and `as_of_join` correctly returns NaN rather than fabricating one. The
majority-vote bias below only counts timeframes that actually have a value.
"""
from __future__ import annotations

import pandas as pd

from app.config import BAR_DURATION, Timeframe

DIRECTION_BULLISH = "BULLISH"
DIRECTION_BEARISH = "BEARISH"
BIAS_MIXED = "MIXED"


def compute_direction(df: pd.DataFrame) -> pd.Series:
    """BULLISH if EMA20 > EMA50, BEARISH otherwise, NaN during EMA20/EMA50 warmup.

    A simple, explicit, documented trend-following heuristic -- not a model prediction.
    Causality is inherited directly from EMA20/EMA50, whose no-lookahead property is already
    verified in Phase 4 (test_no_lookahead_indicators_match_when_computed_on_truncated_series).
    """
    direction = pd.Series(pd.NA, index=df.index, dtype="object")
    has_both = df["EMA20"].notna() & df["EMA50"].notna()
    direction.loc[has_both & (df["EMA20"] > df["EMA50"])] = DIRECTION_BULLISH
    direction.loc[has_both & (df["EMA20"] <= df["EMA50"])] = DIRECTION_BEARISH
    return direction


def _close_time(index: pd.DatetimeIndex, timeframe: Timeframe) -> pd.Series:
    return pd.Series(index + BAR_DURATION[timeframe], index=index)


def as_of_join(
    target_close_time: pd.Series,
    source_direction: pd.Series,
    source_timeframe: Timeframe,
) -> pd.Series:
    """For each timestamp in `target_close_time`, return the value from the most recently
    CLOSED bar in `source_direction` (indexed by that source's own bar-open timestamps) --
    i.e. the last source row whose close time <= the target's close time. NaN if no such row
    exists yet (source history hasn't started, or the source has no value at that point)."""
    source_close_time = _close_time(source_direction.index, source_timeframe)
    source_df = pd.DataFrame({"close_time": source_close_time.values, "value": source_direction.values})
    source_df = source_df.sort_values("close_time")

    target_df = pd.DataFrame({"close_time": target_close_time.values})
    merged = pd.merge_asof(
        target_df, source_df, on="close_time", direction="backward", allow_exact_matches=True
    )
    merged.index = target_close_time.index
    return merged["value"]


def attach_multi_timeframe_bias(
    target_df: pd.DataFrame,
    target_timeframe: Timeframe,
    direction_by_timeframe: dict[Timeframe, pd.Series],
) -> pd.DataFrame:
    """Attach one `{TF}_direction` column per timeframe in `direction_by_timeframe` (each a
    Series from compute_direction(), indexed by that timeframe's own bar-open timestamps) plus
    an overall `mtf_bias` majority vote across whichever timeframes have a value for that row.

    `direction_by_timeframe` should include target_timeframe's own direction series too --
    the spec's multi-timeframe bias example includes the target timeframe's own direction
    alongside the other three, and the as-of join against one's own series is a correct
    identity match (a bar is always "available" as of its own close time).
    """
    df = target_df.copy()
    target_close_time = _close_time(df.index, target_timeframe)

    direction_cols: list[str] = []
    for tf, direction_series in direction_by_timeframe.items():
        col = f"{tf.value}_direction"
        df[col] = as_of_join(target_close_time, direction_series, tf)
        direction_cols.append(col)

    def _majority_vote(row: pd.Series) -> object:
        votes = [v for v in row if v in (DIRECTION_BULLISH, DIRECTION_BEARISH)]
        if not votes:
            return pd.NA
        bulls, bears = votes.count(DIRECTION_BULLISH), votes.count(DIRECTION_BEARISH)
        if bulls > bears:
            return DIRECTION_BULLISH
        if bears > bulls:
            return DIRECTION_BEARISH
        return BIAS_MIXED

    df["mtf_bias"] = df[direction_cols].apply(_majority_vote, axis=1)
    return df
