"""Phase 13 tests for the data routers: 404 handling with synthetic (empty) data directories,
plus a real end-to-end smoke test against this project's actual generated data (data/features/,
models/, data/news/) -- skipped automatically on a fresh clone where those gitignored,
reproducible-via-script directories don't exist yet."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_DATA = (PROJECT_ROOT / "data" / "features").glob("EURUSD_D1_*.parquet")
HAS_REAL_DATA = any(True for _ in HAS_REAL_DATA)


def test_market_analysis_404_when_no_data(tmp_path):
    with patch("app.features.feature_engineering.FEATURES_DIR", tmp_path):
        response = client.get("/api/market-analysis/EURUSD/D1")
    assert response.status_code == 404


def test_explainability_404_when_no_report(tmp_path):
    with patch("app.services.repository.MODELS_DIR", tmp_path):
        response = client.get("/api/explainability/EURUSD/D1/random_forest")
    assert response.status_code == 404


def test_walk_forward_404_when_no_report(tmp_path):
    with patch("app.services.repository.MODELS_DIR", tmp_path):
        response = client.get("/api/walk-forward/EURUSD/D1")
    assert response.status_code == 404


def test_backtesting_404_when_no_report(tmp_path):
    with patch("app.services.repository.MODELS_DIR", tmp_path):
        response = client.get("/api/backtesting/EURUSD/D1/random_forest")
    assert response.status_code == 404


def test_performance_by_regime_404_when_no_data(tmp_path):
    with patch("app.services.repository.MODELS_DIR", tmp_path):
        response = client.get("/api/backtesting/EURUSD/D1/random_forest/performance-by-regime")
    assert response.status_code == 404


def test_model_lab_returns_200_with_nulls_when_no_reports(tmp_path):
    with patch("app.services.repository.MODELS_DIR", tmp_path):
        response = client.get("/api/model-lab/EURUSD/D1")
    assert response.status_code == 200
    assert response.json() == {
        "asset_key": "EURUSD", "timeframe": "D1", "baseline_comparison": None, "walk_forward": None,
    }


def test_news_sentiment_returns_200_empty_when_no_scored_news(tmp_path):
    with patch("app.sentiment.pipeline.SCORED_NEWS_PATH", tmp_path / "missing.parquet"):
        response = client.get("/api/news-sentiment/EURUSD")
    assert response.status_code == 200
    assert response.json()["articles"] == []


def test_invalid_asset_returns_422():
    response = client.get("/api/market-analysis/NOTANASSET/D1")
    assert response.status_code == 422


def test_invalid_timeframe_returns_422():
    response = client.get("/api/market-analysis/EURUSD/NOTATIMEFRAME")
    assert response.status_code == 422


@pytest.mark.skipif(not HAS_REAL_DATA, reason="Real generated data (data/features/) not present -- run the pipeline phases first.")
class TestRealData:
    """Exercises every data endpoint against this project's actual generated artifacts, not
    synthetic fixtures -- the strongest possible verification, mirroring the manual check
    already done for this phase."""

    def test_market_analysis_real(self):
        response = client.get("/api/market-analysis/EURUSD/D1?limit=5")
        assert response.status_code == 200
        body = response.json()
        assert body["current_price"] > 0
        assert len(body["bars"]) == 5

    def test_predictions_real(self):
        response = client.get("/api/predictions/XAUUSD/D1")
        assert response.status_code == 200
        body = response.json()
        assert body["consensus_class"] in ("BUY", "HOLD", "SELL")
        assert len(body["predictions"]) == 4

    def test_explainability_real(self):
        response = client.get("/api/explainability/XAUUSD/D1/svm")
        assert response.status_code == 200
        assert len(response.json()["local_explanations"][0]["top_factors"]) > 0

    def test_model_lab_real(self):
        response = client.get("/api/model-lab/XAUUSD/D1")
        assert response.status_code == 200
        assert response.json()["baseline_comparison"] is not None

    def test_walk_forward_real(self):
        response = client.get("/api/walk-forward/XAUUSD/D1")
        assert response.status_code == 200
        assert response.json()["n_resolved_windows"] > 0

    def test_backtesting_real(self):
        response = client.get("/api/backtesting/XAUUSD/D1/svm")
        assert response.status_code == 200
        assert response.json()["summary"]["num_trades"] > 0

    def test_performance_by_regime_real(self):
        response = client.get("/api/backtesting/XAUUSD/D1/svm/performance-by-regime")
        assert response.status_code == 200
        assert len(response.json()) > 0

    def test_news_sentiment_real(self):
        response = client.get("/api/news-sentiment/EURUSD?limit=3")
        assert response.status_code == 200
        assert len(response.json()["articles"]) > 0
