"""Phase 10 tests for app.sentiment.news_data. Uses a small temp CSV -- no dependency on the
real sample_headlines.csv or on FinBERT/torch."""
from __future__ import annotations

import pytest

from app.sentiment import news_data


def _write_sample_csv(path):
    path.write_text(
        "published_at,asset_key,headline,generated_tone\n"
        "2024-01-02T10:00:00+00:00,EURUSD,EUR/USD rallies as data beats forecasts,positive\n"
        "2024-01-01T09:00:00+00:00,BTCUSD,BTC/USD slides on regulatory concerns,negative\n"
        "2024-01-03T11:00:00+00:00,EURUSD,EUR/USD little changed in quiet trading,neutral\n"
    )


def test_load_news_parses_timestamps_and_sorts(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_sample_csv(csv_path)

    df = news_data.load_news(path=csv_path)
    assert len(df) == 3
    assert df["published_at"].is_monotonic_increasing
    assert str(df["published_at"].dt.tz) == "UTC"


def test_load_news_filters_by_asset(tmp_path):
    csv_path = tmp_path / "sample.csv"
    _write_sample_csv(csv_path)

    df = news_data.load_news(asset_key="EURUSD", path=csv_path)
    assert len(df) == 2
    assert set(df["asset_key"]) == {"EURUSD"}


def test_load_news_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="No news data"):
        news_data.load_news(path=tmp_path / "does_not_exist.csv")
