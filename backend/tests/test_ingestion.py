"""Phase 2 tests for app.services.ingestion.

These are unit tests against a mocked yfinance — no network access, so they run fast and
deterministically in CI. A separate live smoke run against the real yfinance API was done
manually to confirm connectivity and produced the files under data/raw/ (see
docs/data_sources.md); that's not re-run automatically on every test invocation.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.config import Timeframe
from app.services import ingestion


def _fake_ohlcv_df(rows: int = 3) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [1.0] * rows,
            "High": [1.1] * rows,
            "Low": [0.9] * rows,
            "Close": [1.05] * rows,
            "Volume": [100] * rows,
        },
        index=index,
    )


def test_fetch_ohlcv_rejects_h4():
    with pytest.raises(ValueError, match="not fetched directly"):
        ingestion.fetch_ohlcv("EURUSD", Timeframe.H4)


def test_fetch_ohlcv_raises_on_empty_result():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    with patch.object(ingestion.yf, "Ticker", return_value=mock_ticker):
        with pytest.raises(RuntimeError, match="no data"):
            ingestion.fetch_ohlcv("EURUSD", Timeframe.D1)


def test_fetch_ohlcv_returns_dataframe():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _fake_ohlcv_df()
    with patch.object(ingestion.yf, "Ticker", return_value=mock_ticker):
        df = ingestion.fetch_ohlcv("BTCUSD", Timeframe.D1)
    assert len(df) == 3
    mock_ticker.history.assert_called_once_with(period="max", interval="1d")


def test_save_raw_writes_csv_and_manifest_and_never_overwrites(tmp_path):
    with patch.object(ingestion, "RAW_DIR", tmp_path):
        df = _fake_ohlcv_df()
        csv_path, manifest_path = ingestion.save_raw(df, "EURUSD", Timeframe.D1)

        assert csv_path.exists()
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert manifest["asset_key"] == "EURUSD"
        assert manifest["timeframe"] == "D1"
        assert manifest["row_count"] == 3
        assert manifest["source"] == "yfinance"

        # Re-saving under the exact same filename (same timestamp) must refuse, not overwrite.
        fixed_now = ingestion.datetime.fromisoformat(manifest["fetched_at_utc"])

        class _FixedDateTime(ingestion.datetime):
            @classmethod
            def now(cls, tz=None):  # noqa: ANN001 - matches datetime.now signature
                return fixed_now

        with patch.object(ingestion, "datetime", _FixedDateTime):
            with pytest.raises(FileExistsError):
                ingestion.save_raw(df, "EURUSD", Timeframe.D1)


def test_ingest_collects_partial_failures(tmp_path):
    good_df = _fake_ohlcv_df()

    def fake_fetch(asset_key: str, timeframe: Timeframe) -> pd.DataFrame:
        if asset_key == "XAUUSD":
            raise RuntimeError("simulated delisting")
        return good_df

    with patch.object(ingestion, "RAW_DIR", tmp_path), \
         patch.object(ingestion, "fetch_ohlcv", side_effect=fake_fetch):
        results = ingestion.ingest(
            asset_keys=["EURUSD", "XAUUSD"], timeframes=[Timeframe.D1]
        )

    by_asset = {r.asset_key: r for r in results}
    assert by_asset["EURUSD"].ok is True
    assert by_asset["EURUSD"].row_count == 3
    assert by_asset["XAUUSD"].ok is False
    assert "simulated delisting" in by_asset["XAUUSD"].error
