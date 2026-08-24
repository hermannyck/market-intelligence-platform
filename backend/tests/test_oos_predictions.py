"""Phase 12 test for app.validation.walk_forward.generate_oos_predictions -- the function
Phase 12's backtest engine depends on for leakage-free predictions."""
from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import ModelName, Timeframe
from app.validation import walk_forward as wf


def _labeled_features(rows: int, start: str = "2024-06-01", freq: str = "1h", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range(start, periods=rows, freq=freq, tz="UTC")
    from app.ml import models as ml_models

    data = {col: rng.normal(0, 1, rows) for col in ml_models.NUMERIC_FEATURE_COLUMNS}
    for col in ml_models.CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["BULLISH", "BEARISH", "UNKNOWN"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


def test_generate_oos_predictions_covers_only_resolved_test_windows(tmp_path):
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    df = _labeled_features(rows=500, freq="1h")
    stem = "EURUSD_H1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        predictions = wf.generate_oos_predictions("EURUSD", Timeframe.H1, ModelName.RANDOM_FOREST)

    assert len(predictions) > 0
    assert set(predictions.unique()) <= {"BUY", "HOLD", "SELL"}
    assert predictions.index.is_monotonic_increasing

    # Every predicted timestamp must fall within some resolved window's test period -- never
    # inside that same window's own training period (which would mean the model predicted on
    # data it was trained on -- not what "out-of-sample" means).
    from app.ml.models import prepare_dataset

    dataset = prepare_dataset(df)
    resolved = wf.resolve_windows(dataset)
    for ts in predictions.index:
        assert any(w["window"].test_start <= str(ts) <= w["window"].test_end for w in resolved)


def test_generate_oos_predictions_empty_when_no_windows_resolve(tmp_path):
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    df = _labeled_features(rows=10, freq="1h")  # far too little data for any window
    stem = "EURUSD_H1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        predictions = wf.generate_oos_predictions("EURUSD", Timeframe.H1, ModelName.RANDOM_FOREST)

    assert predictions.empty
