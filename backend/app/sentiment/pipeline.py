"""Phase 10 orchestration: score the sample news with FinBERT once (cached, never
overwritten), then join timestamp-aware rolling sentiment features onto the latest
`data/features/` file per asset/timeframe — same "latest = most complete" convention as every
prior phase.

**Timestamp-awareness, precisely.** An article is usable for a bar only if
``published_at <= bar_close_time`` (the same close-time convention as Phase 5's multi-timeframe
alignment: a bar's index is its OPEN time, so it's only "available" at open + duration).
`_windowed_aggregate` computes, for each bar's own close time, the mean/count of articles
published in ``(close_time - window, close_time]`` directly via `searchsorted` + cumulative
sums — evaluated relative to *that bar's own timestamp*, not by finding the nearest article and
reusing a value computed at *that article's* timestamp (an earlier, subtly wrong approach; see
`_windowed_aggregate`'s docstring for the exact bug it replaced). A bar whose window contains no
articles gets NaN for sentiment/probabilities (nothing to average) but 0, not NaN, for
`num_relevant_news` (a real, meaningful count) — never a fabricated "neutral" score.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import ASSETS, BAR_DURATION, SENTIMENT, TIMEFRAMES, Timeframe
from app.features.feature_engineering import FEATURES_DIR, find_latest_features
from app.sentiment.finbert import score_texts
from app.sentiment.news_data import NEWS_DIR, load_news

SCORED_NEWS_PATH = NEWS_DIR / "scored_headlines.parquet"

SENTIMENT_FEATURE_COLUMNS = (
    "sentiment_score",
    "positive_probability",
    "negative_probability",
    "neutral_probability",
    "num_relevant_news",
    "rolling_sentiment_score",
)


def score_all_news(force: bool = False) -> pd.DataFrame:
    """Scores every sample headline with FinBERT once and caches the result. Re-running this
    without `force=True` reuses the cache -- FinBERT inference is deterministic given the same
    model/text, so there's no reason to recompute unless the sample dataset itself changed."""
    if SCORED_NEWS_PATH.exists() and not force:
        return pd.read_parquet(SCORED_NEWS_PATH)

    news = load_news()
    scores = score_texts(news["headline"].tolist())
    scored = pd.concat([news.reset_index(drop=True), scores.reset_index(drop=True)], axis=1)

    SCORED_NEWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(SCORED_NEWS_PATH)
    return scored


def _windowed_aggregate(
    bar_close_time: pd.Series, article_times: pd.Series, article_values: pd.DataFrame, window: str
) -> pd.DataFrame:
    """For each timestamp in `bar_close_time`, aggregate `article_values` (row-aligned with
    `article_times`, both already sorted ascending) over articles published in
    ``(t - window, t]`` -- computed relative to EACH bar's own close time via a cumulative-sum
    + searchsorted, not by looking up the "nearest" article and reusing a rolling-window value
    computed at *that article's own timestamp*.

    That nearest-article approach was tried first and is wrong: if a bar's close time is far
    enough past an article that the window would have "rolled off" by the bar's time, an
    as-of lookup still finds that article as the nearest one and returns its own (now-stale)
    window count/average -- silently showing news as "in range" long after it no longer is.
    Caught by `test_num_relevant_news_is_zero_not_nan_before_any_coverage_gap`.
    """
    window_td = pd.Timedelta(window)
    article_times_arr = article_times.to_numpy()
    bar_times_arr = bar_close_time.to_numpy()

    end_idx = np.searchsorted(article_times_arr, bar_times_arr, side="right")
    start_idx = np.searchsorted(article_times_arr, bar_times_arr - window_td, side="right")
    counts = end_idx - start_idx

    result: dict[str, np.ndarray] = {"count": counts}
    for col in article_values.columns:
        cumsum = np.concatenate([[0.0], np.cumsum(article_values[col].to_numpy())])
        sums = cumsum[end_idx] - cumsum[start_idx]
        with np.errstate(invalid="ignore", divide="ignore"):
            means = sums / np.where(counts > 0, counts, 1)
        result[col] = np.where(counts > 0, means, np.nan)
    return pd.DataFrame(result, index=bar_close_time.index)


def attach_sentiment_features(
    features_df: pd.DataFrame, timeframe: Timeframe, scored_news_for_asset: pd.DataFrame
) -> pd.DataFrame:
    df = features_df.copy()
    bar_close_time = pd.Series(df.index + BAR_DURATION[timeframe], index=df.index)

    if scored_news_for_asset.empty:
        for col in SENTIMENT_FEATURE_COLUMNS:
            df[col] = pd.NA
        return df

    news_sorted = scored_news_for_asset.sort_values("published_at").reset_index(drop=True)
    article_times = news_sorted["published_at"]

    short = _windowed_aggregate(
        bar_close_time, article_times,
        news_sorted[["sentiment_score", "positive_prob", "negative_prob", "neutral_prob"]],
        SENTIMENT.short_window,
    )
    long_ = _windowed_aggregate(
        bar_close_time, article_times, news_sorted[["sentiment_score"]], SENTIMENT.long_window
    )

    df["sentiment_score"] = short["sentiment_score"]
    df["positive_probability"] = short["positive_prob"]
    df["negative_probability"] = short["negative_prob"]
    df["neutral_probability"] = short["neutral_prob"]
    # A bar can genuinely have zero relevant articles in the short window even once news
    # coverage has started (e.g. between two sparse articles) -- that's a real 0, not a
    # missing value, unlike the sentiment score, which has nothing to average in that case.
    df["num_relevant_news"] = short["count"].astype(int)
    df["rolling_sentiment_score"] = long_["sentiment_score"]
    return df


@dataclass
class SentimentResult:
    asset_key: str
    timeframe: str
    row_count: int
    parquet_path: str
    manifest_path: str
    coverage_rows: int


def save_with_sentiment(df: pd.DataFrame, asset_key: str, timeframe: Timeframe, source_manifest: Path) -> tuple[Path, Path]:
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{asset_key}_{timeframe.value}_{stamp}"

    parquet_path = FEATURES_DIR / f"{stem}.parquet"
    manifest_path = FEATURES_DIR / f"{stem}.manifest.json"
    if parquet_path.exists() or manifest_path.exists():
        raise FileExistsError(f"{parquet_path} already exists; refusing to overwrite feature data.")

    df.to_parquet(parquet_path)
    coverage_rows = int(df["sentiment_score"].notna().sum())

    manifest = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(df),
        "includes_sentiment": True,
        "sentiment_coverage_rows": coverage_rows,
        "sentiment_coverage_pct": round(100 * coverage_rows / len(df), 2) if len(df) else 0.0,
        "sentiment_source": "sample_headlines.csv (documented synthetic sample, not a real historical news archive -- see data/news/README.md)",
        "source_features_manifest": str(source_manifest),
        "first_timestamp": str(df.index.min()) if len(df) else None,
        "last_timestamp": str(df.index.max()) if len(df) else None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return parquet_path, manifest_path


def add_sentiment_for_asset_timeframe(asset_key: str, timeframe: Timeframe, scored_news: pd.DataFrame | None = None) -> SentimentResult:
    features_df, source_manifest = find_latest_features(asset_key, timeframe)
    scored_news = scored_news if scored_news is not None else score_all_news()
    asset_news = scored_news[scored_news["asset_key"] == asset_key]

    with_sentiment = attach_sentiment_features(features_df, timeframe, asset_news)
    parquet_path, manifest_path = save_with_sentiment(with_sentiment, asset_key, timeframe, source_manifest)
    return SentimentResult(
        asset_key=asset_key,
        timeframe=timeframe.value,
        row_count=len(with_sentiment),
        parquet_path=str(parquet_path),
        manifest_path=str(manifest_path),
        coverage_rows=int(with_sentiment["sentiment_score"].notna().sum()),
    )


def add_sentiment_for_all(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    scored_news = score_all_news()

    results = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            try:
                r = add_sentiment_for_asset_timeframe(asset_key, timeframe, scored_news)
                results.append(
                    {
                        "asset_key": r.asset_key,
                        "timeframe": r.timeframe,
                        "row_count": r.row_count,
                        "coverage_rows": r.coverage_rows,
                        "parquet_path": r.parquet_path,
                        "manifest_path": r.manifest_path,
                    }
                )
            except (FileNotFoundError, ValueError) as exc:
                results.append({"asset_key": asset_key, "timeframe": timeframe.value, "error": str(exc)})
    return results


if __name__ == "__main__":
    for r in add_sentiment_for_all():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} FAILED: {r['error']}")
        else:
            pct = round(100 * r["coverage_rows"] / r["row_count"], 2) if r["row_count"] else 0
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} rows={r['row_count']:<7} sentiment_coverage={r['coverage_rows']:<6} ({pct}%)")
