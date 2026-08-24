"""Phase 11 integration test for app.explainability.pipeline -- trains one tiny real model,
saves it via joblib exactly like Phase 7 does, then runs the real explainability orchestrator
against it. Marked slow: this exercises the real shap library end-to-end.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest

from app.config import ModelName, Timeframe
from app.explainability import pipeline as ep
from app.ml import models as ml_models


def _tiny_labeled_dataset(rows: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="1D", tz="UTC")
    data = {col: rng.normal(0, 1, rows) for col in ml_models.NUMERIC_FEATURE_COLUMNS}
    for col in ml_models.CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["BULLISH", "BEARISH", "UNKNOWN"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


@pytest.mark.slow
def test_explain_asset_timeframe_model_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    models_dir = tmp_path / "models"
    features_dir.mkdir()
    models_dir.mkdir()

    df = _tiny_labeled_dataset(60)
    stem = "EURUSD_D1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    dataset = ml_models.prepare_dataset(df)
    X, y = dataset[ml_models.ALL_FEATURE_COLUMNS], ml_models.encode_labels(dataset["target"])
    pipeline = ml_models.build_pipelines()[ModelName.RANDOM_FOREST]
    pipeline.fit(X, y)
    model_path = models_dir / "EURUSD_D1_random_forest_20240101T000000Z.joblib"
    joblib.dump(pipeline, model_path)

    with patch.object(ep, "MODELS_DIR", models_dir), \
         patch.object(ml_models, "MODELS_DIR", models_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = ep.explain_asset_timeframe_model("EURUSD", Timeframe.D1, ModelName.RANDOM_FOREST)

    assert Path(result.report_path).exists()
    report = json.loads(Path(result.report_path).read_text())
    assert report["model_name"] == "random_forest"
    assert set(ml_models.NUMERIC_FEATURE_COLUMNS) <= set(report["global_feature_importance"].keys())
    assert len(report["local_explanations"]) == 1
    local = report["local_explanations"][0]
    assert local["predicted_class"] in ml_models.TARGET_LABELS
    assert set(local["probabilities"].keys()) == set(ml_models.TARGET_LABELS)
    assert len(local["top_factors"]) <= 5


def test_find_latest_model_raises_when_missing(tmp_path):
    with patch.object(ep, "MODELS_DIR", tmp_path):
        with pytest.raises(FileNotFoundError, match="No trained"):
            ep.find_latest_model("EURUSD", Timeframe.D1, ModelName.RANDOM_FOREST)
