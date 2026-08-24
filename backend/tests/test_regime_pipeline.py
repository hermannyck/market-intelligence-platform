"""Phase 9 integration tests for app.regime.pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import TIMEFRAMES, Timeframe
from app.regime import pipeline as rp


def _labeled_features(rows: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="1h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.01, rows))
    df = pd.DataFrame(
        {
            "close": close,
            "ATR14": 1.0 + rng.normal(0, 0.02, rows),
            "EMA20": close, "EMA50": close, "EMA200": close,
            "target": rng.choice(["BUY", "HOLD", "SELL"], size=rows),
        },
        index=index,
    )
    df.index.name = "timestamp"
    return df


def test_add_regime_for_asset_timeframe_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    features_dir.mkdir()

    df = _labeled_features()
    stem = "EURUSD_D1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch.object(rp, "FEATURES_DIR", features_dir), \
         patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
        result = rp.add_regime_for_asset_timeframe("EURUSD", Timeframe.D1)

    assert result.row_count == 200
    saved = pd.read_parquet(result.parquet_path)
    assert "regime" in saved.columns
    assert "volatility_zscore" in saved.columns
    assert "trend_strength" in saved.columns
    # original columns (from Phase 6) must survive the regime pass untouched
    assert "target" in saved.columns

    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["includes_regime"] is True
    assert manifest["regime_distribution"]["total_labeled_rows"] > 0
    assert manifest["source_features_manifest"].endswith(f"{stem}.manifest.json")


def test_save_with_regime_never_overwrites(tmp_path):
    df = _labeled_features(50)
    from app.regime.detector import classify_regime

    with_regime = classify_regime(df)
    with patch.object(rp, "FEATURES_DIR", tmp_path):
        parquet_path, manifest_path = rp.save_with_regime(
            with_regime, "EURUSD", Timeframe.D1, Path("some/source.json")
        )
        assert parquet_path.exists()

        fixed_now = rp.datetime.fromisoformat(json.loads(manifest_path.read_text())["built_at_utc"])

        class _FixedDateTime(rp.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                return fixed_now

        with patch.object(rp, "datetime", _FixedDateTime):
            with pytest.raises(FileExistsError):
                rp.save_with_regime(with_regime, "EURUSD", Timeframe.D1, Path("x"))


def test_add_regime_for_all_collects_errors(tmp_path):
    with patch.object(rp, "FEATURES_DIR", tmp_path), \
         patch("app.features.feature_engineering.FEATURES_DIR", tmp_path):
        results = rp.add_regime_for_all(asset_keys=["EURUSD"])
    assert len(results) == len(TIMEFRAMES)
    assert all("error" in r for r in results)
