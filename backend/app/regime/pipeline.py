"""Phase 9 orchestration: load the latest `data/features/` file (already includes indicators,
derived features, multi-timeframe bias, and the Phase 6 target), add regime columns, and save
a new, more complete `data/features/` file — same never-overwrite, "latest = most complete"
convention as every prior phase (see `data/features/README.md`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import ASSETS, TIMEFRAMES, Timeframe
from app.features.feature_engineering import FEATURES_DIR, find_latest_features
from app.regime.detector import classify_regime, regime_distribution


@dataclass
class RegimeResult:
    asset_key: str
    timeframe: str
    row_count: int
    parquet_path: str
    manifest_path: str
    distribution: dict


def save_with_regime(df, asset_key: str, timeframe: Timeframe, source_manifest: Path) -> tuple[Path, Path]:
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{asset_key}_{timeframe.value}_{stamp}"

    parquet_path = FEATURES_DIR / f"{stem}.parquet"
    manifest_path = FEATURES_DIR / f"{stem}.manifest.json"
    if parquet_path.exists() or manifest_path.exists():
        raise FileExistsError(f"{parquet_path} already exists; refusing to overwrite feature data.")

    df.to_parquet(parquet_path)
    distribution = regime_distribution(df)

    manifest = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": len(df),
        "includes_regime": True,
        "regime_distribution": distribution,
        "source_features_manifest": str(source_manifest),
        "first_timestamp": str(df.index.min()) if len(df) else None,
        "last_timestamp": str(df.index.max()) if len(df) else None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return parquet_path, manifest_path


def add_regime_for_asset_timeframe(asset_key: str, timeframe: Timeframe) -> RegimeResult:
    features_df, source_manifest = find_latest_features(asset_key, timeframe)
    with_regime = classify_regime(features_df)
    parquet_path, manifest_path = save_with_regime(with_regime, asset_key, timeframe, source_manifest)
    return RegimeResult(
        asset_key=asset_key,
        timeframe=timeframe.value,
        row_count=len(with_regime),
        parquet_path=str(parquet_path),
        manifest_path=str(manifest_path),
        distribution=regime_distribution(with_regime),
    )


def add_regime_for_all(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    results = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            try:
                r = add_regime_for_asset_timeframe(asset_key, timeframe)
                results.append(
                    {
                        "asset_key": r.asset_key,
                        "timeframe": r.timeframe,
                        "row_count": r.row_count,
                        "parquet_path": r.parquet_path,
                        "manifest_path": r.manifest_path,
                        "distribution": r.distribution,
                    }
                )
            except (FileNotFoundError, ValueError) as exc:
                results.append({"asset_key": asset_key, "timeframe": timeframe.value, "error": str(exc)})
    return results


if __name__ == "__main__":
    for r in add_regime_for_all():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} FAILED: {r['error']}")
        else:
            pct = r["distribution"]["percentages"]
            labeled = r["distribution"]["total_labeled_rows"]
            print(
                f"{r['asset_key']:<8} {r['timeframe']:<4} rows={r['row_count']:<7} labeled={labeled:<7} "
                + " ".join(f"{k}={v}%" for k, v in pct.items())
            )
