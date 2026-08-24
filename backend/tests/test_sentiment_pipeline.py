"""Phase 10 tests for app.sentiment.pipeline. FinBERT/torch is never invoked here -- every
test either bypasses scoring by injecting a pre-scored news DataFrame directly, or mocks
`finbert.score_texts`, so this suite runs fully offline regardless of whether torch is
installed.

test_attach_sentiment_features_no_lookahead is the critical one: it reproduces the same
"article published after this bar closed must not be visible to it" hazard Phase 5 proved for
multi-timeframe bars, now for news.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import Timeframe
from app.sentiment import pipeline as sp


def _scored_news(rows: list[tuple[str, str, float]], asset_key: str = "EURUSD") -> pd.DataFrame:
    """rows: list of (published_at_iso, headline, sentiment_score)."""
    records = []
    for ts, headline, score in rows:
        records.append(
            {
                "published_at": pd.Timestamp(ts, tz="UTC"),
                "asset_key": asset_key,
                "headline": headline,
                "positive_prob": max(score, 0.0),
                "negative_prob": max(-score, 0.0),
                "neutral_prob": 1.0 - abs(score),
                "sentiment_score": score,
            }
        )
    return pd.DataFrame(records)


def test_attach_sentiment_features_no_lookahead():
    # One D1 bar at 2024-01-01 (closes 2024-01-02). An article published well before close
    # must be visible; one published after close must NOT be.
    bars = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2024-01-01"], tz="UTC"))
    news = _scored_news(
        [
            ("2024-01-01T10:00:00Z", "before close, should count", 0.8),
            ("2024-01-02T00:00:01Z", "one second after close, must NOT count", -0.9),
        ]
    )
    out = sp.attach_sentiment_features(bars, Timeframe.D1, news)
    # Only the first article should be visible -> sentiment_score should reflect +0.8, not an
    # average that includes the -0.9 future article.
    assert out["sentiment_score"].iloc[0] == pytest.approx(0.8)
    assert out["num_relevant_news"].iloc[0] == 1


def test_attach_sentiment_features_exact_close_time_is_visible():
    bars = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2024-01-01"], tz="UTC"))
    news = _scored_news([("2024-01-02T00:00:00Z", "published exactly at close", 0.5)])
    out = sp.attach_sentiment_features(bars, Timeframe.D1, news)
    assert out["sentiment_score"].iloc[0] == pytest.approx(0.5)


def test_attach_sentiment_features_empty_news_is_all_nan_not_fabricated():
    bars = pd.DataFrame({"close": [1.0, 1.1]}, index=pd.date_range("2024-01-01", periods=2, tz="UTC"))
    out = sp.attach_sentiment_features(bars, Timeframe.D1, pd.DataFrame())
    for col in sp.SENTIMENT_FEATURE_COLUMNS:
        assert out[col].isna().all()


def test_num_relevant_news_is_zero_not_nan_before_any_coverage_gap():
    # Bar far after the only article's short window has rolled off -> 0 relevant articles
    # (a real, meaningful zero), while sentiment_score is NaN (nothing to average).
    bars = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2024-02-01"], tz="UTC"))
    news = _scored_news([("2024-01-01T00:00:00Z", "old news, outside the 24h short window", 0.9)])
    out = sp.attach_sentiment_features(bars, Timeframe.D1, news)
    assert out["num_relevant_news"].iloc[0] == 0
    assert pd.isna(out["sentiment_score"].iloc[0])
    # But the long (7D) rolling_sentiment_score window has also long since rolled off here.
    assert pd.isna(out["rolling_sentiment_score"].iloc[0])


def test_rolling_windows_short_vs_long_differ():
    # D1 bar at 2024-01-05 closes at 2024-01-06T00:00 -> 24h window is (01-05 00:00, 01-06 00:00].
    bars = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2024-01-05"], tz="UTC"))
    news = _scored_news(
        [
            ("2024-01-05T18:00:00Z", "within both the 24h short and 7D long window", 1.0),
            ("2023-12-30T12:00:00Z", "within the 7D long window only, not the 24h short one", -1.0),
        ]
    )
    out = sp.attach_sentiment_features(bars, Timeframe.D1, news)
    # short window (24h before close 2024-01-06) only sees the recent article -> +1.0
    assert out["sentiment_score"].iloc[0] == pytest.approx(1.0)
    # long window (7D) sees both -> averages to 0.0
    assert out["rolling_sentiment_score"].iloc[0] == pytest.approx(0.0)


def test_save_with_sentiment_never_overwrites(tmp_path):
    bars = pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex(["2024-01-01"], tz="UTC"))
    df = sp.attach_sentiment_features(bars, Timeframe.D1, pd.DataFrame())

    with patch.object(sp, "FEATURES_DIR", tmp_path):
        parquet_path, manifest_path = sp.save_with_sentiment(df, "EURUSD", Timeframe.D1, Path("src.json"))
        assert parquet_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["includes_sentiment"] is True
        assert "not a real historical news archive" in manifest["sentiment_source"]

        fixed_now = sp.datetime.fromisoformat(manifest["built_at_utc"])

        class _FixedDateTime(sp.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                return fixed_now

        with patch.object(sp, "datetime", _FixedDateTime):
            with pytest.raises(FileExistsError):
                sp.save_with_sentiment(df, "EURUSD", Timeframe.D1, Path("src.json"))


def test_score_all_news_caches(tmp_path):
    scored_path = tmp_path / "scored.parquet"
    fake_scores = pd.DataFrame(
        {"positive_prob": [0.7], "negative_prob": [0.1], "neutral_prob": [0.2], "sentiment_score": [0.6]}
    )
    fake_news = pd.DataFrame(
        {"published_at": [pd.Timestamp("2024-01-01", tz="UTC")], "asset_key": ["EURUSD"], "headline": ["x"]}
    )

    with patch.object(sp, "SCORED_NEWS_PATH", scored_path), \
         patch.object(sp, "load_news", return_value=fake_news) as mock_load, \
         patch.object(sp, "score_texts", return_value=fake_scores) as mock_score:
        first = sp.score_all_news()
        assert mock_score.call_count == 1
        assert scored_path.exists()

        second = sp.score_all_news()  # should hit the cache, not re-score
        assert mock_score.call_count == 1
        pd.testing.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True))


def test_add_sentiment_for_asset_timeframe_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    features_dir.mkdir()

    close = np.array([1.0, 1.01, 1.02])
    df = pd.DataFrame({"close": close}, index=pd.date_range("2024-01-01", periods=3, freq="1D", tz="UTC"))
    stem = "EURUSD_D1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    scored_news = _scored_news([("2024-01-01T12:00:00Z", "headline", 0.4)])

    with patch.object(sp, "FEATURES_DIR", features_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = sp.add_sentiment_for_asset_timeframe("EURUSD", Timeframe.D1, scored_news)

    assert result.row_count == 3
    saved = pd.read_parquet(result.parquet_path)
    for col in sp.SENTIMENT_FEATURE_COLUMNS:
        assert col in saved.columns
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["includes_sentiment"] is True
