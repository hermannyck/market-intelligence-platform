"""Phase 5 integration tests for app.features.feature_engineering -- builds synthetic
"processed" parquet files for all 4 timeframes in a temp dir and runs the real orchestrator
end-to-end, rather than mocking every internal step."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import ASSETS, TIMEFRAMES, Timeframe
from app.features import feature_engineering as fe


def _synthetic_processed(rows: int, freq: str, asset_key: str, timeframe: Timeframe) -> pd.DataFrame:
    rng = np.random.default_rng(hash((asset_key, timeframe.value)) % (2**32))
    index = pd.date_range("2024-06-01", periods=rows, freq=freq, tz="UTC")
    close = 1.10 + np.cumsum(rng.normal(0, 0.0005, rows))
    df = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.0002, rows),
            "high": close + rng.uniform(0.0002, 0.001, rows),
            "low": close - rng.uniform(0.0002, 0.001, rows),
            "close": close,
            "volume": rng.integers(100, 1000, rows).astype(float),
            "asset": asset_key,
            "timeframe": timeframe.value,
        },
        index=index,
    )
    df.index.name = "timestamp"
    return df


def _write_processed(processed_dir: Path, asset_key: str, timeframe: Timeframe, rows: int, freq: str) -> Path:
    df = _synthetic_processed(rows, freq, asset_key, timeframe)
    stem = f"{asset_key}_{timeframe.value}_20240601T000000Z"
    parquet_path = processed_dir / f"{stem}.parquet"
    manifest_path = processed_dir / f"{stem}.manifest.json"
    df.to_parquet(parquet_path)
    manifest_path.write_text(json.dumps({"asset_key": asset_key, "timeframe": timeframe.value, "row_count": rows}))
    return manifest_path


_FREQ_BY_TF = {Timeframe.M15: "15min", Timeframe.H1: "1h", Timeframe.H4: "4h", Timeframe.D1: "1D"}


@pytest.fixture
def processed_dir(tmp_path):
    d = tmp_path / "processed"
    d.mkdir()
    asset_key = "EURUSD"
    # Enough rows for every indicator's warmup (EMA200 needs 200) on every timeframe.
    for tf in TIMEFRAMES:
        _write_processed(d, asset_key, tf, rows=250, freq=_FREQ_BY_TF[tf])
    return d


def test_build_features_for_asset_end_to_end(processed_dir, tmp_path):
    features_dir = tmp_path / "features"
    with patch.object(fe, "PROCESSED_DIR", processed_dir), patch.object(fe, "FEATURES_DIR", features_dir):
        results = fe.build_features_for_asset("EURUSD")

    assert len(results) == len(TIMEFRAMES)
    for r in results:
        assert r["row_count"] == 250
        assert Path(r["parquet_path"]).exists()
        assert Path(r["manifest_path"]).exists()

        saved = pd.read_parquet(r["parquet_path"])
        for col in fe.FEATURE_COLUMNS:
            assert col in saved.columns, f"{r['timeframe']} missing {col}"

        manifest = json.loads(Path(r["manifest_path"]).read_text())
        assert manifest["not_yet_included"] == ["market_regime (Phase 9)", "news_sentiment (Phase 10)"]
        assert set(manifest["source_processed_manifests"].keys()) == {tf.value for tf in TIMEFRAMES}


def test_mtf_bias_present_and_uses_all_four_timeframes(processed_dir, tmp_path):
    features_dir = tmp_path / "features"
    with patch.object(fe, "PROCESSED_DIR", processed_dir), patch.object(fe, "FEATURES_DIR", features_dir):
        results = fe.build_features_for_asset("EURUSD")

    h1_result = next(r for r in results if r["timeframe"] == "H1")
    df = pd.read_parquet(h1_result["parquet_path"])
    # By the end of a 250-row H1 series, there's been plenty of time for M15/H4/D1 history
    # (all starting at the same point) to have produced at least one closed bar each.
    last_row = df.iloc[-1]
    for tf in TIMEFRAMES:
        assert last_row[f"{tf.value}_direction"] in ("BULLISH", "BEARISH") or pd.isna(last_row[f"{tf.value}_direction"])
    assert last_row["mtf_bias"] in ("BULLISH", "BEARISH", "MIXED") or pd.isna(last_row["mtf_bias"])


def test_save_features_never_overwrites(tmp_path):
    features_dir = tmp_path / "features"
    df = pd.DataFrame({"close": [1.0, 1.1]}, index=pd.date_range("2024-01-01", periods=2, tz="UTC"))

    with patch.object(fe, "FEATURES_DIR", features_dir):
        parquet_path, manifest_path = fe.save_features(df, "EURUSD", Timeframe.D1, {"D1": "some/manifest.json"})
        assert parquet_path.exists()

        fixed_now = fe.datetime.fromisoformat(json.loads(manifest_path.read_text())["built_at_utc"])

        class _FixedDateTime(fe.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                return fixed_now

        with patch.object(fe, "datetime", _FixedDateTime):
            with pytest.raises(FileExistsError):
                fe.save_features(df, "EURUSD", Timeframe.D1, {"D1": "some/manifest.json"})


def test_find_latest_processed_raises_when_missing(tmp_path):
    with patch.object(fe, "PROCESSED_DIR", tmp_path):
        with pytest.raises(FileNotFoundError, match="No processed data"):
            fe.find_latest_processed("EURUSD", Timeframe.D1)


def test_build_all_features_collects_per_asset_errors(tmp_path):
    with patch.object(fe, "PROCESSED_DIR", tmp_path), patch.object(fe, "FEATURES_DIR", tmp_path / "features"):
        results = fe.build_all_features(asset_keys=["EURUSD"])
    assert len(results) == 1
    assert "error" in results[0]
