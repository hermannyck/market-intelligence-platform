"""Phase 6 tests for app.ml.target.

test_target_depends_only_on_exactly_horizon_bars_ahead is the critical one: it's the concrete,
falsifiable version of "the exact leakage boundary" documented in the module docstring --
target[t] must depend on close[t], close[t+horizon], and ATR14[t]/close[t], and nothing else.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.config import TARGET, Timeframe
from app.ml import target as tgt


def _df(close_values: list[float], atr_values: list[float] | None = None) -> pd.DataFrame:
    n = len(close_values)
    index = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    atr = atr_values if atr_values is not None else [0.01] * n
    return pd.DataFrame({"close": close_values, "ATR14": atr}, index=index)


def test_compute_future_return_formula_and_trailing_nan():
    df = _df([1.0, 1.1, 1.21, 1.05, 0.9])
    result = tgt.compute_future_return(df, horizon_bars=2)
    np.testing.assert_allclose(result.iloc[0], 1.21 / 1.0 - 1)
    np.testing.assert_allclose(result.iloc[1], 1.05 / 1.1 - 1)
    np.testing.assert_allclose(result.iloc[2], 0.9 / 1.21 - 1)
    assert result.iloc[3:].isna().all()  # last 2 rows: no future bar yet


def test_compute_volatility_threshold_formula_and_missing_atr():
    df = _df([1.0, 2.0], atr_values=[0.02, 0.04])
    result = tgt.compute_volatility_threshold(df, volatility_multiplier=0.5)
    np.testing.assert_allclose(result, [0.5 * 0.02 / 1.0, 0.5 * 0.04 / 2.0])

    with pytest.raises(ValueError, match="requires an ATR14 column"):
        tgt.compute_volatility_threshold(df.drop(columns=["ATR14"]), volatility_multiplier=0.5)


def test_generate_target_boundary_conditions():
    # threshold[0] = 0.5 * 0.02 / 1.0 = 0.01 = 1%. close[1]/close[0]-1 = 1.1% > 1% -> BUY.
    df = _df([1.0, 1.011, 1.010, 0.989, 1.0], atr_values=[0.02] * 5)
    out = tgt.generate_target(df, horizon_bars=1, volatility_multiplier=0.5)

    assert out["target"].iloc[0] == tgt.BUY
    # every fully-defined row resolves to a real label, never left NaN when both future_return
    # and threshold are available
    assert out["target"].iloc[:-1].isin([tgt.BUY, tgt.HOLD, tgt.SELL]).all()
    # last row has no bar horizon_bars ahead -> NaN target, not fabricated
    assert pd.isna(out["target"].iloc[-1])


def test_label_exact_threshold_is_hold_not_buy_or_sell():
    # Exercises the labeling boundary directly with exact values (bypassing the close-price
    # ratio arithmetic in compute_future_return, which is subject to float rounding and can't
    # reliably hit a bit-exact boundary). BUY/SELL require a strict >, not >=.
    future_return = pd.Series([0.01, -0.01, 0.0100001, -0.0100001])
    threshold = pd.Series([0.01, 0.01, 0.01, 0.01])
    labels = tgt.label_from_return_and_threshold(future_return, threshold)
    assert list(labels) == [tgt.HOLD, tgt.HOLD, tgt.BUY, tgt.SELL]


def test_target_depends_only_on_exactly_horizon_bars_ahead():
    # Two datasets identical through row t + horizon, diverging only after that -- target[t]
    # must be identical between them for every row that has enough lookahead within the
    # shared prefix.
    horizon = 3
    shared_prefix = [1.0, 1.02, 0.99, 1.05, 1.10, 0.95, 1.01]  # length 7
    atr = [0.01] * len(shared_prefix)

    tail_a = [1.20, 1.30, 1.40]  # divergent future beyond the shared prefix
    tail_b = [0.80, 0.70, 0.60]

    df_a = _df(shared_prefix + tail_a, atr_values=atr + [0.01] * 3)
    df_b = _df(shared_prefix + tail_b, atr_values=atr + [0.01] * 3)

    out_a = tgt.generate_target(df_a, horizon_bars=horizon, volatility_multiplier=0.5)
    out_b = tgt.generate_target(df_b, horizon_bars=horizon, volatility_multiplier=0.5)

    # Rows 0..(len(shared_prefix)-horizon-1) have their target-defining window entirely
    # within the shared prefix -> must match exactly between the two divergent datasets.
    safe_upto = len(shared_prefix) - horizon
    pd.testing.assert_series_equal(
        out_a["target"].iloc[:safe_upto], out_b["target"].iloc[:safe_upto], check_names=False
    )
    pd.testing.assert_series_equal(
        out_a["future_return"].iloc[:safe_upto],
        out_b["future_return"].iloc[:safe_upto],
        check_names=False,
    )


def test_class_balance_report_counts_and_imbalance_flag():
    df = pd.DataFrame({"target": ["BUY", "BUY", "HOLD", "HOLD", "HOLD", "HOLD", "SELL", None]})
    report = tgt.class_balance_report(df)
    assert report["total_labeled_rows"] == 7
    assert report["counts"] == {"HOLD": 4, "BUY": 2, "SELL": 1}
    assert report["dominant_class"] == "HOLD"
    assert report["percentages"]["HOLD"] == pytest.approx(57.14, abs=0.01)
    assert report["is_imbalanced"] is False  # 57% < 80% default threshold

    skewed = pd.DataFrame({"target": ["HOLD"] * 9 + ["BUY"]})
    report2 = tgt.class_balance_report(skewed)
    assert report2["is_imbalanced"] is True


def test_save_labeled_features_never_overwrites(tmp_path):
    df = tgt.generate_target(_df([1.0, 1.01, 1.02, 1.03]), horizon_bars=1, volatility_multiplier=0.5)
    with patch.object(tgt, "FEATURES_DIR", tmp_path):
        parquet_path, manifest_path = tgt.save_labeled_features(
            df, "EURUSD", Timeframe.D1, Path("some/source.manifest.json"), 1, 0.5
        )
        assert parquet_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["includes_target"] is True
        assert manifest["target_config"] == {"horizon_bars": 1, "volatility_multiplier": 0.5}

        fixed_now = tgt.datetime.fromisoformat(manifest["built_at_utc"])

        class _FixedDateTime(tgt.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                return fixed_now

        with patch.object(tgt, "datetime", _FixedDateTime):
            with pytest.raises(FileExistsError):
                tgt.save_labeled_features(df, "EURUSD", Timeframe.D1, Path("x"), 1, 0.5)


def test_add_target_for_asset_timeframe_end_to_end(tmp_path):
    features_dir = tmp_path / "features"
    features_dir.mkdir()

    df = _df([1.0 + i * 0.001 for i in range(50)], atr_values=[0.01] * 50)
    stem = "EURUSD_D1_20240101T000000Z"
    df.to_parquet(features_dir / f"{stem}.parquet")
    (features_dir / f"{stem}.manifest.json").write_text(json.dumps({"asset_key": "EURUSD"}))

    with patch.object(tgt, "FEATURES_DIR", features_dir):
        with patch("app.features.feature_engineering.FEATURES_DIR", features_dir):
            result = tgt.add_target_for_asset_timeframe("EURUSD", Timeframe.D1)

    assert result.row_count == 50
    assert Path(result.parquet_path).exists()
    saved = pd.read_parquet(result.parquet_path)
    assert "target" in saved.columns
    assert "future_return" in saved.columns
    manifest = json.loads(Path(result.manifest_path).read_text())
    assert manifest["includes_target"] is True
    assert manifest["trailing_rows_without_future_data"] == TARGET.horizon_bars
