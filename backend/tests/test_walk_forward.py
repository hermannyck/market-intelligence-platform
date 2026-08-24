"""Phase 8 tests for app.validation.walk_forward."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import Timeframe, WalkForwardWindow
from app.ml import models as ml_models
from app.validation import walk_forward as wf


def _synthetic_labeled_features(rows: int, start: str = "2024-01-01", freq: str = "1h", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range(start, periods=rows, freq=freq, tz="UTC")
    data = {col: rng.normal(0, 1, rows) for col in ml_models.NUMERIC_FEATURE_COLUMNS}
    for col in [f"{tf.value}_direction" for tf in [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1]]:
        data[col] = rng.choice(["BULLISH", "BEARISH", None], size=rows, p=[0.4, 0.4, 0.2])
    data["mtf_bias"] = rng.choice(["BULLISH", "BEARISH", "MIXED"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    data["future_return"] = rng.normal(0, 0.01, rows)
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


def test_resolve_configured_windows_marks_applicability_by_min_rows():
    df = _synthetic_labeled_features(rows=100, start="2024-01-01", freq="1D")
    windows = (
        WalkForwardWindow("2024-01-01", "2024-02-01", "2024-02-02", "2024-03-01"),  # plenty of rows
        WalkForwardWindow("2019-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),  # zero rows, no data that far back
    )
    resolved = wf.resolve_configured_windows(df, windows, min_rows=10)
    assert resolved[0]["applicable"] is True
    assert resolved[0]["train_rows"] > 0
    assert resolved[1]["applicable"] is False
    assert resolved[1]["train_rows"] == 0


def test_generate_fallback_windows_expanding_train_sliding_test():
    df = _synthetic_labeled_features(rows=500, freq="1h")
    resolved = wf.generate_fallback_windows(df, n_windows=4, min_rows=10)
    assert len(resolved) == 4
    for r in resolved:
        assert r["source"] == "auto_generated_fallback"
        assert r["applicable"] is True
    # train size must strictly grow window over window (expanding window)
    train_sizes = [r["train_rows"] for r in resolved]
    assert train_sizes == sorted(train_sizes)
    assert train_sizes[0] < train_sizes[-1]


def test_generate_fallback_windows_returns_empty_when_too_little_data():
    df = _synthetic_labeled_features(rows=20, freq="1h")
    resolved = wf.generate_fallback_windows(df, n_windows=4, min_rows=30)
    assert resolved == []


def test_resolve_windows_falls_back_when_no_configured_window_applies():
    # Data entirely in 2024 -- none of the real 2021-2025 configured windows (which expect
    # 2021-2024 train data) will have any training rows for a series that starts in 2024.
    df = _synthetic_labeled_features(rows=400, start="2024-06-01", freq="1h")
    resolved = wf.resolve_windows(df)
    assert len(resolved) > 0
    assert all(r["source"] == "auto_generated_fallback" for r in resolved)


def test_compute_trading_metrics_basic_and_edge_cases():
    # 2 wins, 1 loss on BUY; 1 win on SELL (predicted SELL, price fell -> -(-0.01) = +0.01)
    preds = np.array(["BUY", "BUY", "BUY", "SELL", "HOLD"])
    future_returns = np.array([0.02, 0.01, -0.01, -0.01, 0.5])  # HOLD's return must be ignored
    result = wf.compute_trading_metrics(preds, future_returns)
    assert result["num_trades"] == 4
    assert result["win_rate"] == pytest.approx(0.75)  # 3 of 4 trades profitable
    assert result["profit_factor"] > 1  # more won than lost here
    assert result["max_drawdown"] <= 0
    assert result["sharpe_ratio"] is not None

    # No trades at all -> everything None, not a crash
    empty = wf.compute_trading_metrics(np.array(["HOLD", "HOLD"]), np.array([0.1, -0.1]))
    assert empty["num_trades"] == 0
    assert empty["win_rate"] is None

    # No losing trades -> profit_factor undefined (None), not a fake "infinity"
    all_wins = wf.compute_trading_metrics(np.array(["BUY", "BUY"]), np.array([0.01, 0.02]))
    assert all_wins["profit_factor"] is None
    assert all_wins["win_rate"] == 1.0


def test_evaluate_with_roc_auc_handles_missing_class_gracefully():
    df = ml_models.prepare_dataset(_synthetic_labeled_features(200))
    train, test = ml_models.chronological_split(df)
    X_train, y_train = train[ml_models.ALL_FEATURE_COLUMNS], ml_models.encode_labels(train["target"])
    X_test = test[ml_models.ALL_FEATURE_COLUMNS]
    # Force a test set with only one class present -- ROC-AUC is undefined here.
    y_test_single_class = np.zeros(len(test), dtype=int)

    from app.config import ModelName

    pipeline = ml_models.build_pipelines()[ModelName.RANDOM_FOREST]
    pipeline.fit(X_train, y_train)
    metrics = wf.evaluate_with_roc_auc(pipeline, X_test, y_test_single_class)
    assert metrics["roc_auc_macro"] is None
    assert "accuracy" in metrics  # the rest of evaluate() still ran fine


def test_aggregate_across_windows_computes_mean_std_and_excludes_none():
    per_window_results = [
        {"models": {"random_forest": {"accuracy": 0.4, "roc_auc_macro": None, "trading": {"win_rate": 0.5}}}},
        {"models": {"random_forest": {"accuracy": 0.6, "roc_auc_macro": 0.55, "trading": {"win_rate": 0.6}}}},
    ]
    overall = wf.aggregate_across_windows(per_window_results)
    rf = overall["random_forest"]
    assert rf["accuracy_mean"] == pytest.approx(0.5)
    assert rf["accuracy_n_windows"] == 2
    assert rf["roc_auc_macro_n_windows"] == 1  # the None was excluded, not averaged as 0
    assert rf["trading_win_rate_mean"] == pytest.approx(0.55)


def test_run_walk_forward_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    models_dir = tmp_path / "models"
    features_dir.mkdir()

    df = _synthetic_labeled_features(rows=600, freq="1h")
    stem = "EURUSD_H1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch.object(wf, "MODELS_DIR", models_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = wf.run_walk_forward("EURUSD", Timeframe.H1)

    assert result["n_windows"] > 0
    assert result["window_source"] == "auto_generated_fallback"  # 2024-only data, no configured window fits
    report = json.loads(Path(result["report_path"]).read_text())
    assert len(report["windows"]) == result["n_windows"]
    for window_report in report["windows"]:
        for model_name, metrics in window_report["models"].items():
            assert "trading" in metrics
            assert "roc_auc_macro" in metrics
    assert set(report["overall"].keys()) == {"logistic_regression", "random_forest", "svm", "xgboost"}
