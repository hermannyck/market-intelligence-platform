"""Phase 12 integration test for app.backtesting.pipeline -- runs the real walk-forward OOS
prediction generator + the real backtest engine end-to-end against a synthetic dataset.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import ModelName, Timeframe
from app.backtesting import pipeline as bp
from app.ml import models as ml_models


def _labeled_features_with_ohlc(rows: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-06-01", periods=rows, freq="1h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.1, rows))
    data = {col: rng.normal(0, 1, rows) for col in ml_models.NUMERIC_FEATURE_COLUMNS}
    for col in ml_models.CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["BULLISH", "BEARISH", "UNKNOWN"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    data["open"] = close
    data["high"] = close + rng.uniform(0.05, 0.2, rows)
    data["low"] = close - rng.uniform(0.05, 0.2, rows)
    data["close"] = close
    data["ATR14"] = rng.uniform(0.5, 1.5, rows)
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


def test_run_backtest_for_asset_timeframe_model_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    models_dir = tmp_path / "models"
    features_dir.mkdir()

    df = _labeled_features_with_ohlc()
    stem = "EURUSD_H1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch.object(bp, "MODELS_DIR", models_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = bp.run_backtest_for_asset_timeframe_model("EURUSD", Timeframe.H1, ModelName.RANDOM_FOREST)

    assert Path(result.report_path).exists()
    report = json.loads(Path(result.report_path).read_text())
    assert report["model_name"] == "random_forest"
    assert "num_trades" in report["summary"]
    assert "equity_curve" in report
    assert len(report["equity_curve"]) > 0
    assert report["num_oos_predictions"] > 0


def test_run_backtest_raises_when_no_oos_predictions(tmp_path):
    features_dir = tmp_path / "features"
    models_dir = tmp_path / "models"
    features_dir.mkdir()

    df = _labeled_features_with_ohlc(rows=10)  # far too little data -> no resolved windows
    stem = "EURUSD_H1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch.object(bp, "MODELS_DIR", models_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        with pytest.raises(ValueError, match="No out-of-sample"):
            bp.run_backtest_for_asset_timeframe_model("EURUSD", Timeframe.H1, ModelName.RANDOM_FOREST)
