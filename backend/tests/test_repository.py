"""Phase 13 tests for app.services.repository -- the file-backed layer routers call into.
Uses small synthetic files (tmp_path), mirroring the pattern from every prior phase's
integration tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest

from app.config import ModelName, Timeframe
from app.ml import models as ml_models
from app.services import repository as repo


def _full_dataset(rows: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="1D", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.1, rows))
    data = {col: rng.normal(0, 1, rows) for col in ml_models.NUMERIC_FEATURE_COLUMNS}
    for col in ml_models.CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["BULLISH", "BEARISH", "UNKNOWN"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    data["open"] = close
    data["high"] = close + 0.2
    data["low"] = close - 0.2
    data["close"] = close
    data["ATR14"] = 1.0
    data["regime"] = rng.choice(["Sideways / Range-Bound", "High Volatility", "Low Volatility"], size=rows)
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


@pytest.fixture
def features_dir(tmp_path):
    d = tmp_path / "features"
    d.mkdir()
    df = _full_dataset()
    stem = "EURUSD_D1_20240101T000000Z"
    df.to_parquet(d / f"{stem}.parquet")
    (d / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))
    return d


def test_market_analysis_shape(features_dir):
    with patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = repo.market_analysis("EURUSD", Timeframe.D1, limit=10)

    assert result["asset_key"] == "EURUSD"
    assert len(result["bars"]) == 10
    assert "M15_direction" in result["multi_timeframe_bias"]
    assert result["regime"]["current_regime"] in (
        "Sideways / Range-Bound", "High Volatility", "Low Volatility",
    )
    assert result["regime"]["regime_distribution"]["total_labeled_rows"] == 60


def test_predictions_with_consensus(tmp_path, features_dir):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    df = _full_dataset()
    dataset = ml_models.prepare_dataset(df)
    X, y = dataset[ml_models.ALL_FEATURE_COLUMNS], ml_models.encode_labels(dataset["target"])
    for model_name, pipeline in ml_models.build_pipelines().items():
        pipeline.fit(X, y)
        joblib.dump(pipeline, models_dir / f"EURUSD_D1_{model_name.value}_20240101T000000Z.joblib")

    with patch("app.features.feature_engineering.FEATURES_DIR", features_dir), \
         patch.object(ml_models, "MODELS_DIR", models_dir), \
         patch("app.explainability.pipeline.MODELS_DIR", models_dir):
        result = repo.predictions_with_consensus("EURUSD", Timeframe.D1)

    assert len(result["predictions"]) == 4
    assert result["consensus_class"] in ("BUY", "HOLD", "SELL")
    assert "/4" in result["consensus_ratio"]


def test_predictions_with_consensus_no_models_returns_empty(features_dir, tmp_path):
    models_dir = tmp_path / "empty_models"
    models_dir.mkdir()
    with patch("app.features.feature_engineering.FEATURES_DIR", features_dir), \
         patch.object(ml_models, "MODELS_DIR", models_dir), \
         patch("app.explainability.pipeline.MODELS_DIR", models_dir):
        result = repo.predictions_with_consensus("EURUSD", Timeframe.D1)
    assert result["predictions"] == []
    assert result["consensus_class"] is None


def test_latest_explainability_report(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    payload = {"model_name": "random_forest", "global_feature_importance": {"RSI14": 0.5}}
    (models_dir / "EURUSD_D1_random_forest_explainability_20240101T000000Z.json").write_text(json.dumps(payload))

    with patch.object(repo, "MODELS_DIR", models_dir):
        result = repo.latest_explainability_report("EURUSD", Timeframe.D1, ModelName.RANDOM_FOREST)
    assert result["model_name"] == "random_forest"

    with patch.object(repo, "MODELS_DIR", models_dir):
        missing = repo.latest_explainability_report("EURUSD", Timeframe.D1, ModelName.SVM)
    assert missing is None


def test_model_lab_combines_baseline_and_walk_forward(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "EURUSD_D1_baseline_comparison_20240101T000000Z.json").write_text(json.dumps({"models": {}}))
    (models_dir / "EURUSD_D1_walk_forward_20240101T000000Z.json").write_text(json.dumps({"overall": {}}))

    with patch.object(repo, "MODELS_DIR", models_dir):
        result = repo.model_lab("EURUSD", Timeframe.D1)
    assert result["baseline_comparison"] == {"models": {}}
    assert result["walk_forward"] == {"overall": {}}


def test_model_performance_by_regime_joins_trades_with_regime(features_dir, tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    df = _full_dataset()
    trades = [
        {"entry_time": str(df.index[5]), "net_return_pct": 0.02},
        {"entry_time": str(df.index[10]), "net_return_pct": -0.01},
    ]
    backtest = {"trades": trades, "summary": {}}
    (models_dir / "EURUSD_D1_svm_backtest_20240101T000000Z.json").write_text(json.dumps(backtest))

    with patch.object(repo, "MODELS_DIR", models_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = repo.model_performance_by_regime("EURUSD", Timeframe.D1, ModelName.SVM)

    assert result is not None
    total_trades = sum(v["num_trades"] for v in result.values())
    assert total_trades == 2


def test_model_performance_by_regime_none_when_no_backtest(tmp_path):
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    with patch.object(repo, "MODELS_DIR", models_dir):
        result = repo.model_performance_by_regime("EURUSD", Timeframe.D1, ModelName.SVM)
    assert result is None


def test_news_sentiment_filters_by_asset(tmp_path):
    news_dir = tmp_path / "news"
    news_dir.mkdir()
    scored_path = news_dir / "scored_headlines.parquet"
    df = pd.DataFrame(
        {
            "published_at": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
            "asset_key": ["EURUSD", "BTCUSD"],
            "headline": ["euro news", "btc news"],
            "sentiment_score": [0.5, -0.2],
            "positive_prob": [0.6, 0.1],
            "negative_prob": [0.1, 0.5],
            "neutral_prob": [0.3, 0.4],
        }
    )
    df.to_parquet(scored_path)

    with patch("app.sentiment.pipeline.SCORED_NEWS_PATH", scored_path):
        result = repo.news_sentiment("EURUSD")
    assert len(result["articles"]) == 1
    assert result["articles"][0]["headline"] == "euro news"


def test_news_sentiment_missing_file_returns_note(tmp_path):
    with patch("app.sentiment.pipeline.SCORED_NEWS_PATH", tmp_path / "does_not_exist.parquet"):
        result = repo.news_sentiment("EURUSD")
    assert result["articles"] == []
    assert "note" in result
