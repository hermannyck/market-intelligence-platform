"""Phase 5: assemble the final feature sets in ``data/features/``.

Pipeline stage: ``data/processed/`` (Phase 3) -> indicators (Phase 4,
``app.features.indicators``) -> derived/relationship features (``app.features.derived``) ->
multi-timeframe bias (``app.features.multi_timeframe``) -> ``data/features/``.

For each asset, all four timeframes' processed data is loaded and run through the indicator
pipeline first (every timeframe needs its own EMA20/EMA50-derived `direction`, regardless of
which timeframe is the current *target*), then each timeframe's full feature set is built
using that shared pool of per-timeframe directions for the multi-timeframe bias lookup.

**Not included yet, by design**: market regime (Phase 9) and news sentiment (Phase 10)
features. Adding NaN placeholder columns for them now would just be dead weight until those
phases exist; when they land, they extend this schema via a timestamp+asset join rather than
requiring a rebuild of everything here. See ``data/features/README.md``.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import ASSETS, TIMEFRAMES, Timeframe
from app.features.derived import DERIVED_COLUMNS, add_all_derived_features
from app.features.indicators import INDICATOR_COLUMNS, add_all_indicators
from app.features.multi_timeframe import attach_multi_timeframe_bias, compute_direction

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FEATURES_DIR = PROJECT_ROOT / "data" / "features"

FEATURE_COLUMNS = (
    list(INDICATOR_COLUMNS)
    + list(DERIVED_COLUMNS)
    + [f"{tf.value}_direction" for tf in TIMEFRAMES]
    + ["mtf_bias"]
)


@dataclass
class TimeframeData:
    timeframe: Timeframe
    processed_df: pd.DataFrame
    with_indicators: pd.DataFrame
    direction: pd.Series
    source_manifest: Path


def find_latest_processed(asset_key: str, timeframe: Timeframe) -> tuple[pd.DataFrame, Path]:
    manifests = sorted(PROCESSED_DIR.glob(f"{asset_key}_{timeframe.value}_*.manifest.json"))
    if not manifests:
        raise FileNotFoundError(
            f"No processed data for {asset_key} {timeframe.value} in {PROCESSED_DIR}. "
            "Run `python -m app.services.cleaning` first."
        )
    manifest_path = manifests[-1]
    parquet_path = manifest_path.with_suffix("").with_suffix(".parquet")
    return pd.read_parquet(parquet_path), manifest_path


def load_all_timeframes(asset_key: str) -> dict[Timeframe, TimeframeData]:
    """Load + compute indicators + compute direction for every timeframe of one asset. Every
    target timeframe's multi-timeframe bias needs all four, so this is done once up front
    rather than per-target-timeframe."""
    result: dict[Timeframe, TimeframeData] = {}
    for tf in TIMEFRAMES:
        processed_df, manifest_path = find_latest_processed(asset_key, tf)
        with_indicators = add_all_indicators(processed_df)
        direction = compute_direction(with_indicators)
        result[tf] = TimeframeData(
            timeframe=tf,
            processed_df=processed_df,
            with_indicators=with_indicators,
            direction=direction,
            source_manifest=manifest_path,
        )
    return result


def build_feature_set(target_timeframe: Timeframe, all_timeframes: dict[Timeframe, TimeframeData]) -> pd.DataFrame:
    target = all_timeframes[target_timeframe]
    df = add_all_derived_features(target.with_indicators)
    direction_by_tf = {tf: data.direction for tf, data in all_timeframes.items()}
    df = attach_multi_timeframe_bias(df, target_timeframe, direction_by_tf)
    return df


def save_features(
    df: pd.DataFrame, asset_key: str, timeframe: Timeframe, source_manifests: dict[str, str]
) -> tuple[Path, Path]:
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    built_at = datetime.now(timezone.utc)
    stamp = built_at.strftime("%Y%m%dT%H%M%SZ")
    stem = f"{asset_key}_{timeframe.value}_{stamp}"

    parquet_path = FEATURES_DIR / f"{stem}.parquet"
    manifest_path = FEATURES_DIR / f"{stem}.manifest.json"
    if parquet_path.exists() or manifest_path.exists():
        raise FileExistsError(f"{parquet_path} already exists; refusing to overwrite feature data.")

    df.to_parquet(parquet_path)

    warmup_nan_counts = {col: int(df[col].isna().sum()) for col in FEATURE_COLUMNS if col in df.columns}
    manifest = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "built_at_utc": built_at.isoformat(),
        "row_count": len(df),
        "first_timestamp": str(df.index.min()) if len(df) else None,
        "last_timestamp": str(df.index.max()) if len(df) else None,
        "source_processed_manifests": source_manifests,
        "feature_columns": FEATURE_COLUMNS,
        "warmup_or_missing_nan_counts": warmup_nan_counts,
        "not_yet_included": ["market_regime (Phase 9)", "news_sentiment (Phase 10)"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return parquet_path, manifest_path


def build_features_for_asset(asset_key: str) -> list[dict]:
    all_timeframes = load_all_timeframes(asset_key)
    source_manifests = {tf.value: str(data.source_manifest) for tf, data in all_timeframes.items()}

    results = []
    for tf in TIMEFRAMES:
        feature_df = build_feature_set(tf, all_timeframes)
        parquet_path, manifest_path = save_features(feature_df, asset_key, tf, source_manifests)
        results.append(
            {
                "asset_key": asset_key,
                "timeframe": tf.value,
                "row_count": len(feature_df),
                "parquet_path": str(parquet_path),
                "manifest_path": str(manifest_path),
            }
        )
    return results


def build_all_features(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    results = []
    for asset_key in asset_keys:
        try:
            results.extend(build_features_for_asset(asset_key))
        except FileNotFoundError as exc:
            results.append({"asset_key": asset_key, "error": str(exc)})
    return results


if __name__ == "__main__":
    for r in build_all_features():
        if "error" in r:
            print(f"{r['asset_key']:<8} FAILED: {r['error']}")
        else:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} rows={r['row_count']}")
