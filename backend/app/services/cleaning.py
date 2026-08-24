"""Phase 3: data cleaning — raw yfinance pulls -> standardized, validated ``data/processed/``.

Pipeline stage: ``data/raw/`` (Phase 2, immutable, source-native schema/timezone) ->
``data/processed/`` (this module: UTC-normalized, standardized columns, validated OHLC,
documented gaps). Nothing here fabricates data — gaps (weekends, exchange downtime) are
reported, never filled or interpolated, and dropped rows are counted, never silently lost.

H4 is not present in ``data/raw/`` at all (see ``app/services/ingestion.py``); this module
derives it by resampling cleaned H1 bars, keeping only buckets where all four constituent H1
bars are present — a partial/incomplete bucket is dropped rather than treated as an available
prediction-time bar. See ``docs/leakage_prevention.md`` for the full rationale.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import ASSETS, Timeframe

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Expected bar spacing per timeframe, used only to *report* gaps (weekends, exchange
# downtime) for human/EDA review -- never to fabricate or fill missing bars.
_EXPECTED_BAR_SPACING = {
    Timeframe.M15: pd.Timedelta(minutes=15),
    Timeframe.H1: pd.Timedelta(hours=1),
    Timeframe.H4: pd.Timedelta(hours=4),
    Timeframe.D1: pd.Timedelta(days=1),
}

_RAW_OHLCV_COLUMNS = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


@dataclass
class CleaningStats:
    rows_in: int = 0
    duplicates_dropped: int = 0
    nan_dropped: int = 0
    invalid_ohlc_dropped: int = 0
    non_positive_price_dropped: int = 0
    rows_out: int = 0


@dataclass
class GapSummary:
    gap_count: int
    largest_gap_hours: float
    top_gaps: list[dict]  # [{"start": iso, "end": iso, "hours": float}, ...]


def find_latest_raw(asset_key: str, timeframe: Timeframe) -> tuple[Path, Path]:
    """Locate the most recently fetched raw CSV+manifest for an asset/timeframe."""
    manifests = sorted(RAW_DIR.glob(f"{asset_key}_{timeframe.value}_*.manifest.json"))
    if not manifests:
        raise FileNotFoundError(
            f"No raw data for {asset_key} {timeframe.value} in {RAW_DIR}. "
            "Run `python -m app.services.ingestion` first."
        )
    latest_manifest = manifests[-1]  # filenames are UTC-timestamped -> lexical sort == time sort
    csv_path = latest_manifest.with_suffix("").with_suffix(".csv")
    return csv_path, latest_manifest


def load_raw(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, index_col=0)
    # utc=True (rather than parse_dates=True above) is required: raw index strings can mix
    # UTC offsets within a single file (e.g. EUR/USD's exchange timezone observes DST), which
    # makes plain parse_dates produce an object-dtype Index instead of a real DatetimeIndex.
    df.index = pd.to_datetime(df.index, utc=True)
    df.index.name = "timestamp"
    return df


def standardize(df: pd.DataFrame, asset_key: str, timeframe: Timeframe) -> pd.DataFrame:
    """Normalize to UTC, rename to the canonical schema, drop yfinance-only columns."""
    df = df.copy()
    df.index = df.index.tz_convert("UTC")
    df = df.rename(columns=_RAW_OHLCV_COLUMNS)
    df = df[[c for c in _RAW_OHLCV_COLUMNS.values() if c in df.columns]]
    df["asset"] = asset_key
    df["timeframe"] = timeframe.value
    return df


def validate_and_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningStats]:
    """Drop duplicates/NaNs/invalid OHLC. Never fills or interpolates — only removes rows
    that are provably bad, and counts every removal."""
    stats = CleaningStats(rows_in=len(df))

    df = df.sort_index()
    before = len(df)
    df = df[~df.index.duplicated(keep="last")]
    stats.duplicates_dropped = before - len(df)

    before = len(df)
    df = df.dropna(subset=["open", "high", "low", "close"])
    stats.nan_dropped = before - len(df)

    before = len(df)
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    stats.non_positive_price_dropped = before - len(df)

    before = len(df)
    valid_ohlc = (
        (df["high"] >= df[["open", "close", "low"]].max(axis=1))
        & (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    df = df[valid_ohlc]
    stats.invalid_ohlc_dropped = before - len(df)

    stats.rows_out = len(df)
    return df, stats


def analyze_gaps(df: pd.DataFrame, timeframe: Timeframe, top_n: int = 10) -> GapSummary:
    """Report time gaps larger than the expected bar spacing. Purely diagnostic — gaps
    (weekend closures, exchange downtime) are never filled."""
    expected = _EXPECTED_BAR_SPACING[timeframe]
    deltas = df.index.to_series().diff().dropna()
    gaps = deltas[deltas > expected]
    if gaps.empty:
        return GapSummary(gap_count=0, largest_gap_hours=0.0, top_gaps=[])

    gap_records = [
        {
            "start": str(ts - delta),
            "end": str(ts),
            "hours": round(delta.total_seconds() / 3600, 2),
        }
        for ts, delta in gaps.items()
    ]
    gap_records.sort(key=lambda r: r["hours"], reverse=True)
    return GapSummary(
        gap_count=len(gap_records),
        largest_gap_hours=gap_records[0]["hours"],
        top_gaps=gap_records[:top_n],
    )


def resample_h4_from_h1(df_h1_clean: pd.DataFrame, asset_key: str) -> pd.DataFrame:
    """Derive H4 bars from cleaned H1 bars. A bucket is kept only if all 4 constituent H1
    bars are present -- a partial trailing bucket (e.g. the raw pull ends mid-block) is
    dropped rather than emitted as an incomplete/leaky bar. See module docstring."""
    ohlc = df_h1_clean[["open", "high", "low", "close", "volume"]]
    grouped = ohlc.resample("4h", closed="left", label="left", origin="start_day")

    counts = grouped["close"].count()
    complete_buckets = counts[counts == 4].index

    agg = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    h4 = agg.loc[agg.index.isin(complete_buckets)].copy()
    h4["asset"] = asset_key
    h4["timeframe"] = Timeframe.H4.value
    h4.index.name = "timestamp"
    return h4


def save_processed(
    df: pd.DataFrame,
    asset_key: str,
    timeframe: Timeframe,
    cleaning_stats: CleaningStats | None,
    gap_summary: GapSummary,
    source_manifest: Path | None,
    derived_note: str = "",
) -> tuple[Path, Path]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    processed_at = datetime.now(timezone.utc)
    stamp = processed_at.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{asset_key}_{timeframe.value}_{stamp}"

    parquet_path = PROCESSED_DIR / f"{stem}.parquet"
    manifest_path = PROCESSED_DIR / f"{stem}.manifest.json"
    if parquet_path.exists() or manifest_path.exists():
        raise FileExistsError(f"{parquet_path} already exists; refusing to overwrite processed data.")

    df.to_parquet(parquet_path)

    manifest = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "processed_at_utc": processed_at.isoformat(),
        "row_count": len(df),
        "first_timestamp": str(df.index.min()) if len(df) else None,
        "last_timestamp": str(df.index.max()) if len(df) else None,
        "source_raw_manifest": str(source_manifest) if source_manifest else None,
        "derived_note": derived_note,
        "cleaning_stats": asdict(cleaning_stats) if cleaning_stats else None,
        "gap_summary": asdict(gap_summary),
        "columns": list(df.columns),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return parquet_path, manifest_path


def clean_asset_timeframe(asset_key: str, timeframe: Timeframe) -> dict:
    """Load the latest raw pull for one (asset, timeframe), clean it, and save to processed.
    Returns the cleaned DataFrame alongside the result dict so callers (e.g. the H4 step)
    can reuse it without re-reading from disk."""
    csv_path, manifest_path = find_latest_raw(asset_key, timeframe)
    raw = load_raw(csv_path)
    standardized = standardize(raw, asset_key, timeframe)
    cleaned, stats = validate_and_clean(standardized)
    gaps = analyze_gaps(cleaned, timeframe)
    parquet_path, out_manifest_path = save_processed(
        cleaned, asset_key, timeframe, stats, gaps, source_manifest=manifest_path
    )
    return {
        "asset_key": asset_key,
        "timeframe": timeframe.value,
        "df": cleaned,
        "parquet_path": str(parquet_path),
        "manifest_path": str(out_manifest_path),
        "cleaning_stats": asdict(stats),
        "gap_summary": asdict(gaps),
    }


def clean_all(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    results: list[dict] = []

    for asset_key in asset_keys:
        h1_result = None
        for timeframe in (Timeframe.M15, Timeframe.H1, Timeframe.D1):
            try:
                result = clean_asset_timeframe(asset_key, timeframe)
                results.append({k: v for k, v in result.items() if k != "df"})
                if timeframe == Timeframe.H1:
                    h1_result = result
            except FileNotFoundError as exc:
                results.append({"asset_key": asset_key, "timeframe": timeframe.value, "error": str(exc)})

        if h1_result is not None:
            h4_df = resample_h4_from_h1(h1_result["df"], asset_key)
            h4_gaps = analyze_gaps(h4_df, Timeframe.H4)
            parquet_path, manifest_path = save_processed(
                h4_df,
                asset_key,
                Timeframe.H4,
                cleaning_stats=None,
                gap_summary=h4_gaps,
                source_manifest=Path(h1_result["manifest_path"]),
                derived_note="Resampled from cleaned H1; buckets missing any of their 4 H1 bars were dropped.",
            )
            results.append(
                {
                    "asset_key": asset_key,
                    "timeframe": "H4",
                    "parquet_path": str(parquet_path),
                    "manifest_path": str(manifest_path),
                    "row_count": len(h4_df),
                    "gap_summary": asdict(h4_gaps),
                }
            )
    return results


if __name__ == "__main__":
    all_results = clean_all()
    for r in all_results:
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} FAILED: {r['error']}")
        else:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} rows={r.get('row_count', '?')}")
