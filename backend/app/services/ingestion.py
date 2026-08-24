"""Phase 2: historical data ingestion from yfinance into ``data/raw/``.

Design constraints (see ``docs/data_sources.md`` and ``docs/leakage_prevention.md``):

- **Raw data is immutable.** Every fetch is written to a new, uniquely-timestamped file —
  nothing here ever overwrites or edits an existing file in ``data/raw/``. If a pull fails
  or returns no rows, nothing is written at all (no empty/junk files).
- **H4 is not fetched directly.** yfinance has no native 4-hour interval; H4 is derived by
  resampling H1 data in Phase 3 (cleaning/processing), not invented here. Only M15, H1, and
  D1 are pulled from the source.
- **Every fetch is fully provenanced.** Each CSV gets a sibling ``.manifest.json`` recording
  the ticker, requested interval/period, whether the asset is a documented proxy (e.g. XAU/USD
  via gold futures), the actual row count and date range returned, and the UTC time of the
  pull — so any later analysis can point at exactly the raw snapshot it used.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.config import ASSETS, TIMEFRAME_DATA_DEPTH, Timeframe

logger = logging.getLogger(__name__)

# backend/app/services/ingestion.py -> parents[3] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# H4 is derived downstream (Phase 3), never fetched directly — see module docstring.
DIRECTLY_INGESTIBLE_TIMEFRAMES: tuple[Timeframe, ...] = (Timeframe.M15, Timeframe.H1, Timeframe.D1)

# yfinance's actual honored lookback per interval, used as the `period` argument.
_PERIOD_BY_TIMEFRAME = {
    Timeframe.M15: "60d",
    Timeframe.H1: "730d",
    Timeframe.D1: "max",
}


@dataclass
class FetchResult:
    asset_key: str
    timeframe: str
    ok: bool
    row_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    csv_path: str | None = None
    manifest_path: str | None = None
    error: str | None = None


def fetch_ohlcv(asset_key: str, timeframe: Timeframe) -> pd.DataFrame:
    """Pull raw OHLCV history for one asset/timeframe from yfinance. Raises on empty result."""
    if timeframe not in DIRECTLY_INGESTIBLE_TIMEFRAMES:
        raise ValueError(
            f"{timeframe.value} is not fetched directly — it's derived from H1 in Phase 3."
        )
    asset = ASSETS[asset_key]
    depth = TIMEFRAME_DATA_DEPTH[timeframe]
    interval = depth["yfinance_interval"]
    period = _PERIOD_BY_TIMEFRAME[timeframe]

    df = yf.Ticker(asset.yfinance_ticker).history(period=period, interval=interval)
    if df.empty:
        raise RuntimeError(
            f"yfinance returned no data for {asset_key} ({asset.yfinance_ticker}) "
            f"at interval={interval} period={period}"
        )
    return df


def save_raw(df: pd.DataFrame, asset_key: str, timeframe: Timeframe) -> tuple[Path, Path]:
    """Write a fetch to data/raw/ as a new, uniquely-timestamped CSV + manifest. Never overwrites."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    asset = ASSETS[asset_key]
    depth = TIMEFRAME_DATA_DEPTH[timeframe]
    fetched_at = datetime.now(timezone.utc)
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{asset_key}_{timeframe.value}_{stamp}"

    csv_path = RAW_DIR / f"{stem}.csv"
    manifest_path = RAW_DIR / f"{stem}.manifest.json"
    if csv_path.exists() or manifest_path.exists():
        # Timestamp collision (same-second re-run) — refuse rather than overwrite.
        raise FileExistsError(f"{csv_path} already exists; refusing to overwrite raw data.")

    df.to_csv(csv_path)

    manifest = {
        "asset_key": asset_key,
        "asset_code": asset.code,
        "yfinance_ticker": asset.yfinance_ticker,
        "is_proxy": asset.is_proxy,
        "proxy_note": asset.proxy_note,
        "timeframe": timeframe.value,
        "yfinance_interval": depth["yfinance_interval"],
        "requested_period": _PERIOD_BY_TIMEFRAME[timeframe],
        "fetched_at_utc": fetched_at.isoformat(),
        "row_count": len(df),
        "first_timestamp": str(df.index.min()),
        "last_timestamp": str(df.index.max()),
        "source_index_timezone": str(df.index.tz),
        "columns": list(df.columns),
        "source": "yfinance",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return csv_path, manifest_path


def ingest(
    asset_keys: list[str] | None = None,
    timeframes: list[Timeframe] | None = None,
) -> list[FetchResult]:
    """Fetch and save every (asset, timeframe) combination requested. Never raises on a
    single failure — collects a FetchResult per combination so one bad pull (e.g. a
    delisted ticker) doesn't abort the whole run."""
    asset_keys = asset_keys or list(ASSETS.keys())
    timeframes = timeframes or list(DIRECTLY_INGESTIBLE_TIMEFRAMES)

    results: list[FetchResult] = []
    for asset_key in asset_keys:
        for timeframe in timeframes:
            try:
                df = fetch_ohlcv(asset_key, timeframe)
                csv_path, manifest_path = save_raw(df, asset_key, timeframe)
                results.append(
                    FetchResult(
                        asset_key=asset_key,
                        timeframe=timeframe.value,
                        ok=True,
                        row_count=len(df),
                        first_timestamp=str(df.index.min()),
                        last_timestamp=str(df.index.max()),
                        csv_path=str(csv_path),
                        manifest_path=str(manifest_path),
                    )
                )
                logger.info("Ingested %s %s: %d rows", asset_key, timeframe.value, len(df))
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the batch
                results.append(
                    FetchResult(
                        asset_key=asset_key,
                        timeframe=timeframe.value,
                        ok=False,
                        error=str(exc),
                    )
                )
                logger.warning("Failed to ingest %s %s: %s", asset_key, timeframe.value, exc)
    return results


def _print_summary(results: list[FetchResult]) -> None:
    print(f"{'asset':<10} {'timeframe':<6} {'status':<8} {'rows':>6}  range")
    for r in results:
        status = "OK" if r.ok else "FAILED"
        rows = str(r.row_count) if r.ok else "-"
        detail = f"{r.first_timestamp} -> {r.last_timestamp}" if r.ok else r.error
        print(f"{r.asset_key:<10} {r.timeframe:<6} {status:<8} {rows:>6}  {detail}")
    ok_count = sum(1 for r in results if r.ok)
    print(f"\n{ok_count}/{len(results)} fetches succeeded.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    all_results = ingest()
    _print_summary(all_results)
    print(json.dumps([asdict(r) for r in all_results], indent=2))
