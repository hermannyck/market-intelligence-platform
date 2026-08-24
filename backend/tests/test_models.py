"""Phase 7 tests for app.ml.models. Uses small synthetic datasets throughout -- fast, and big
enough to exercise every code path (all 4 models, one-hot categoricals, chronological split).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import ModelName, Timeframe
from app.ml import models


def _synthetic_labeled_features(rows: int = 300, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="1h", tz="UTC")
    data = {col: rng.normal(0, 1, rows) for col in models.NUMERIC_FEATURE_COLUMNS}
    for col in [f"{tf.value}_direction" for tf in [Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1]]:
        data[col] = rng.choice(["BULLISH", "BEARISH", None], size=rows, p=[0.4, 0.4, 0.2])
    data["mtf_bias"] = rng.choice(["BULLISH", "BEARISH", "MIXED"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    data["close"] = 1.0 + np.cumsum(rng.normal(0, 0.001, rows))
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


def test_encode_decode_labels_roundtrip():
    y = pd.Series(["BUY", "HOLD", "SELL", "HOLD"])
    encoded = models.encode_labels(y)
    assert set(encoded) <= {0, 1, 2}
    decoded = models.decode_labels(encoded)
    assert list(decoded) == list(y)


def test_prepare_dataset_categorical_unknown_and_numeric_dropna():
    df = _synthetic_labeled_features(50)
    df.loc[df.index[0], "EMA20"] = np.nan  # numeric NaN -> row must be dropped
    df.loc[df.index[1], "target"] = None  # missing target -> row must be dropped

    out = models.prepare_dataset(df)
    assert df.index[0] not in out.index
    assert df.index[1] not in out.index
    for col in models.CATEGORICAL_FEATURE_COLUMNS:
        assert out[col].isna().sum() == 0
        if df[col].isna().any():
            assert "UNKNOWN" in out[col].unique()
    assert out[models.NUMERIC_FEATURE_COLUMNS].isna().sum().sum() == 0


def test_chronological_split_respects_order_and_rejects_unsorted():
    df = _synthetic_labeled_features(100)
    train, test = models.chronological_split(df, train_fraction=0.8)
    assert len(train) == 80
    assert len(test) == 20
    assert train.index.max() < test.index.min()

    with pytest.raises(ValueError, match="sorted ascending"):
        models.chronological_split(df.iloc[::-1])


def test_build_pipelines_has_all_four_models():
    pipelines = models.build_pipelines()
    assert set(pipelines.keys()) == {
        ModelName.LOGISTIC_REGRESSION,
        ModelName.RANDOM_FOREST,
        ModelName.SVM,
        ModelName.XGBOOST,
    }


def _numeric_transformer(pipeline):
    transformers = pipeline.named_steps["preprocess"].transformers
    return next(transformer for name, transformer, _cols in transformers if name == "numeric")


def test_lr_and_svm_scale_numeric_rf_and_xgb_do_not():
    pipelines = models.build_pipelines()
    for scaled_model in (ModelName.LOGISTIC_REGRESSION, ModelName.SVM):
        assert _numeric_transformer(pipelines[scaled_model]).__class__.__name__ == "StandardScaler"
    for unscaled_model in (ModelName.RANDOM_FOREST, ModelName.XGBOOST):
        assert _numeric_transformer(pipelines[unscaled_model]) == "passthrough"


def test_evaluate_produces_expected_metric_keys_and_confusion_matrix_shape():
    df = models.prepare_dataset(_synthetic_labeled_features(200))
    train, test = models.chronological_split(df)
    X_train, y_train = train[models.ALL_FEATURE_COLUMNS], models.encode_labels(train["target"])
    X_test, y_test = test[models.ALL_FEATURE_COLUMNS], models.encode_labels(test["target"])

    pipeline = models.build_pipelines()[ModelName.RANDOM_FOREST]
    pipeline.fit(X_train, y_train)
    metrics = models.evaluate(pipeline, X_test, y_test)

    for key in ("accuracy", "precision_macro", "recall_macro", "f1_macro", "confusion_matrix"):
        assert key in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert len(metrics["confusion_matrix"]) == 3
    assert all(len(row) == 3 for row in metrics["confusion_matrix"])
    assert metrics["confusion_matrix_labels"] == models.TARGET_LABELS


def test_save_model_never_overwrites(tmp_path):
    df = models.prepare_dataset(_synthetic_labeled_features(100))
    train, _ = models.chronological_split(df)
    X_train, y_train = train[models.ALL_FEATURE_COLUMNS], models.encode_labels(train["target"])
    pipeline = models.build_pipelines()[ModelName.LOGISTIC_REGRESSION]
    pipeline.fit(X_train, y_train)

    with patch.object(models, "MODELS_DIR", tmp_path):
        path1 = models.save_model(pipeline, "EURUSD", Timeframe.D1, ModelName.LOGISTIC_REGRESSION)
        assert path1.exists()
        with pytest.raises(FileExistsError):
            models.save_model(pipeline, "EURUSD", Timeframe.D1, ModelName.LOGISTIC_REGRESSION)


def test_train_baseline_models_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    models_dir = tmp_path / "models"
    features_dir.mkdir()

    df = _synthetic_labeled_features(300)
    stem = "EURUSD_D1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch.object(models, "MODELS_DIR", models_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = models.train_baseline_models("EURUSD", Timeframe.D1)

    assert result.train_rows + result.test_rows <= 300
    assert set(result.per_model.keys()) == {"logistic_regression", "random_forest", "svm", "xgboost"}
    for model_name, metrics in result.per_model.items():
        assert 0.0 <= metrics["accuracy"] <= 1.0
        assert Path(metrics["model_path"]).exists()
    assert Path(result.report_path).exists()
    report = json.loads(Path(result.report_path).read_text())
    assert report["split_method"] == "chronological (no shuffle)"
    assert set(report["models"].keys()) == {"logistic_regression", "random_forest", "svm", "xgboost"}
