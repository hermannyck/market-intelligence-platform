"""Phase 3 tests for app.services.cleaning. All synthetic in-memory data -- no dependency
on files actually produced by ingestion, so these run offline and deterministically."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from app.config import Timeframe
from app.services import cleaning


def _raw_df(rows: int, tz: str = "UTC", freq: str = "1h") -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq=freq, tz=tz)
    return pd.DataFrame(
        {
            "Open": [1.0 + i * 0.01 for i in range(rows)],
            "High": [1.05 + i * 0.01 for i in range(rows)],
            "Low": [0.95 + i * 0.01 for i in range(rows)],
            "Close": [1.02 + i * 0.01 for i in range(rows)],
            "Volume": [100] * rows,
            "Dividends": [0.0] * rows,
            "Stock Splits": [0.0] * rows,
        },
        index=index,
    )


def test_standardize_converts_tz_and_renames_columns():
    raw = _raw_df(3, tz="US/Eastern")
    out = cleaning.standardize(raw, "XAUUSD", Timeframe.H1)
    assert str(out.index.tz) == "UTC"
    assert list(out.columns) == ["open", "high", "low", "close", "volume", "asset", "timeframe"]
    assert (out["asset"] == "XAUUSD").all()
    assert (out["timeframe"] == "H1").all()


def test_validate_and_clean_drops_bad_rows():
    df = cleaning.standardize(_raw_df(5), "EURUSD", Timeframe.H1)
    # duplicate an index entry
    df = pd.concat([df, df.iloc[[0]]]).sort_index()
    # inject a NaN row
    df.iloc[1, df.columns.get_loc("close")] = None
    # inject a non-positive price
    df.iloc[2, df.columns.get_loc("open")] = -1.0
    # inject an invalid OHLC row (high below low)
    df.iloc[3, df.columns.get_loc("high")] = 0.01

    cleaned, stats = cleaning.validate_and_clean(df)

    assert stats.duplicates_dropped == 1
    assert stats.nan_dropped == 1
    assert stats.non_positive_price_dropped == 1
    assert stats.invalid_ohlc_dropped == 1
    assert stats.rows_out == len(cleaned)
    assert cleaned.index.is_monotonic_increasing
    assert not cleaned.index.duplicated().any()


def test_analyze_gaps_detects_gap_larger_than_expected():
    df = cleaning.standardize(_raw_df(3), "EURUSD", Timeframe.H1)
    # remove the middle bar to create a 2-hour gap where 1 hour was expected
    df = df.drop(df.index[1])
    summary = cleaning.analyze_gaps(df, Timeframe.H1)
    assert summary.gap_count == 1
    assert summary.largest_gap_hours == pytest.approx(2.0)


def test_analyze_gaps_no_gaps():
    df = cleaning.standardize(_raw_df(5), "EURUSD", Timeframe.H1)
    summary = cleaning.analyze_gaps(df, Timeframe.H1)
    assert summary.gap_count == 0
    assert summary.top_gaps == []


def test_resample_h4_drops_incomplete_trailing_bucket():
    # 10 hourly bars starting exactly at midnight UTC -> 2 complete 4h buckets (8 bars) +
    # 1 incomplete trailing bucket (2 bars), which must be dropped.
    raw = _raw_df(10)
    df_h1 = cleaning.standardize(raw, "BTCUSD", Timeframe.H1)
    df_h1, _ = cleaning.validate_and_clean(df_h1)

    h4 = cleaning.resample_h4_from_h1(df_h1, "BTCUSD")

    assert len(h4) == 2
    assert (h4["timeframe"] == "H4").all()
    first_bucket = df_h1.iloc[0:4]
    assert h4.iloc[0]["open"] == first_bucket.iloc[0]["open"]
    assert h4.iloc[0]["close"] == first_bucket.iloc[-1]["close"]
    assert h4.iloc[0]["high"] == first_bucket["high"].max()
    assert h4.iloc[0]["low"] == first_bucket["low"].min()
    assert h4.iloc[0]["volume"] == first_bucket["volume"].sum()


def test_save_processed_never_overwrites(tmp_path):
    df = cleaning.standardize(_raw_df(3), "EURUSD", Timeframe.D1)
    df, stats = cleaning.validate_and_clean(df)
    gaps = cleaning.analyze_gaps(df, Timeframe.D1)

    with patch.object(cleaning, "PROCESSED_DIR", tmp_path):
        parquet_path, manifest_path = cleaning.save_processed(
            df, "EURUSD", Timeframe.D1, stats, gaps, source_manifest=None
        )
        assert parquet_path.exists()
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["row_count"] == len(df)
        assert manifest["cleaning_stats"]["rows_out"] == stats.rows_out

        fixed_now = cleaning.datetime.fromisoformat(manifest["processed_at_utc"])

        class _FixedDateTime(cleaning.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001
                return fixed_now

        with patch.object(cleaning, "datetime", _FixedDateTime):
            with pytest.raises(FileExistsError):
                cleaning.save_processed(df, "EURUSD", Timeframe.D1, stats, gaps, source_manifest=None)


def test_clean_asset_timeframe_end_to_end(tmp_path):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()

    raw = _raw_df(5)
    csv_path = raw_dir / "EURUSD_D1_20240101T000000Z.csv"
    manifest_path = raw_dir / "EURUSD_D1_20240101T000000Z.manifest.json"
    raw.to_csv(csv_path)
    manifest_path.write_text(json.dumps({"asset_key": "EURUSD", "timeframe": "D1"}))

    with patch.object(cleaning, "RAW_DIR", raw_dir), patch.object(cleaning, "PROCESSED_DIR", processed_dir):
        result = cleaning.clean_asset_timeframe("EURUSD", Timeframe.D1)

    assert result["cleaning_stats"]["rows_out"] == 5
    assert Path(result["parquet_path"]).exists()
    saved = pd.read_parquet(result["parquet_path"])
    assert len(saved) == 5
    assert list(saved["asset"].unique()) == ["EURUSD"]
