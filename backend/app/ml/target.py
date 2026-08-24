"""Phase 6: target generation — BUY / HOLD / SELL from future price movement (spec Section 5).

    future_return[t] = close[t + horizon_bars] / close[t] - 1
    threshold[t]      = volatility_multiplier * (ATR14[t] / close[t])

    target[t] = BUY   if future_return[t]  >  threshold[t]
              = SELL  if future_return[t]  < -threshold[t]
              = HOLD  otherwise

Both `horizon_bars` and `volatility_multiplier` come from ``app.config.TARGET`` — configurable,
not hardcoded, per the spec's explicit requirement.

**Why volatility-adjusted, not a fixed threshold.** A fixed cutoff (e.g. "> 0.1% = BUY") means
something completely different for EUR/USD (moves ~0.1-0.5%/day) than for BTC/USD (moves
several % in a day) — a fixed threshold would either trivially trigger constantly for BTC or
almost never for EUR/USD, producing exactly the "arbitrary thresholds and excessive class
imbalance" the spec calls out as a risk. Scaling the threshold by each row's own
`ATR14[t]/close[t]` (a normalized volatility measure, already computed and already verified
no-lookahead in Phase 4) makes the BUY/SELL bar adapt to how volatile that asset/timeframe/
period actually was *up to that point* — using only information available at t.

**The exact leakage boundary**, stated precisely: `target[t]` is a function of `close[t]`,
`close[t + horizon_bars]`, and `ATR14[t]`/`close[t]` — nothing else. In particular it does not
depend on any bar beyond `t + horizon_bars`. This is a deliberate, narrow, auditable boundary,
and is verified directly by `test_target_depends_only_on_exactly_horizon_bars_ahead`.

**The horizon is in bars, not wall-clock time** — 12 bars of D1 (calendar weekdays only, gaps
skip weekends automatically) is not the same wall-clock span as 12 bars of M15. This is
intentional: it's a trading-time horizon ("12 bars from now, whenever the market is next
open"), not a fixed calendar duration, which is the standard convention in technical analysis.

**Trailing rows are always NaN, never fabricated.** The last `horizon_bars` rows of any
dataset have no future bar yet to compute `future_return` from. These rows keep `target = NaN`
here (not dropped, not filled) — Phase 7 decides how to handle them when assembling the
training set (typically: drop rows with no target, same as warmup NaNs from earlier phases).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.config import ASSETS, TARGET, Timeframe
from app.features.feature_engineering import FEATURES_DIR, find_latest_features

BUY = "BUY"
HOLD = "HOLD"
SELL = "SELL"


def compute_future_return(df: pd.DataFrame, horizon_bars: int) -> pd.Series:
    """future_return[t] = close[t+horizon_bars] / close[t] - 1. The last `horizon_bars` rows
    are NaN by construction -- there is no future bar for them yet."""
    return df["close"].shift(-horizon_bars) / df["close"] - 1


def compute_volatility_threshold(df: pd.DataFrame, volatility_multiplier: float) -> pd.Series:
    """volatility_multiplier * ATR14[t]/close[t] -- both already available at t."""
    if "ATR14" not in df.columns:
        raise ValueError(
            "compute_volatility_threshold requires an ATR14 column "
            "(run app.features.indicators.add_all_indicators / feature_engineering first)."
        )
    return volatility_multiplier * (df["ATR14"] / df["close"])


def label_from_return_and_threshold(future_return: pd.Series, threshold: pd.Series) -> pd.Series:
    """BUY if future_return > threshold, SELL if future_return < -threshold, HOLD otherwise
    (note: exactly-at-the-boundary is HOLD, not BUY/SELL -- '>' and '<', not '>=' / '<=').
    NaN wherever either input is NaN (never fabricated)."""
    label = pd.Series(pd.NA, index=future_return.index, dtype="object")
    has_both = future_return.notna() & threshold.notna()
    label.loc[has_both & (future_return > threshold)] = BUY
    label.loc[has_both & (future_return < -threshold)] = SELL
    label.loc[has_both & (future_return.abs() <= threshold)] = HOLD
    return label


def generate_target(
    df: pd.DataFrame,
    horizon_bars: int | None = None,
    volatility_multiplier: float | None = None,
) -> pd.DataFrame:
    horizon_bars = TARGET.horizon_bars if horizon_bars is None else horizon_bars
    volatility_multiplier = (
        TARGET.volatility_multiplier if volatility_multiplier is None else volatility_multiplier
    )

    df = df.copy()
    df["future_return"] = compute_future_return(df, horizon_bars)
    df["target_threshold"] = compute_volatility_threshold(df, volatility_multiplier)
    df["target"] = label_from_return_and_threshold(df["future_return"], df["target_threshold"])
    return df


def class_balance_report(
    df: pd.DataFrame, target_col: str = "target", imbalance_warning_threshold: float = 0.80
) -> dict:
    """Counts/percentages of each label among rows that actually have one, plus a simple
    imbalance flag -- surfaced, not auto-corrected. The spec asks target generation to avoid
    "excessive class imbalance"; this makes that visible (in every manifest and the EDA
    notebook) rather than silently trusting the volatility-adjusted threshold got it right."""
    labeled = df[target_col].dropna()
    total = len(labeled)
    counts = {k: int(v) for k, v in labeled.value_counts().items()}
    percentages = {k: round(v / total * 100, 2) for k, v in counts.items()} if total else {}
    dominant = max(percentages, key=percentages.get) if percentages else None
    is_imbalanced = bool(percentages) and (max(percentages.values()) / 100) > imbalance_warning_threshold
    return {
        "total_labeled_rows": total,
        "counts": counts,
        "percentages": percentages,
        "dominant_class": dominant,
        "is_imbalanced": is_imbalanced,
        "imbalance_warning_threshold_pct": round(imbalance_warning_threshold * 100, 2),
    }


@dataclass
class TargetResult:
    asset_key: str
    timeframe: str
    parquet_path: str
    manifest_path: str
    row_count: int
    class_balance: dict


def save_labeled_features(
    df: pd.DataFrame,
    asset_key: str,
    timeframe: Timeframe,
    source_manifest: Path,
    horizon_bars: int,
    volatility_multiplier: float,
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
    balance = class_balance_report(df)

    manifest = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "built_at_utc": built_at.isoformat(),
        "row_count": len(df),
        "includes_target": True,
        "target_config": {
            "horizon_bars": horizon_bars,
            "volatility_multiplier": volatility_multiplier,
        },
        "class_balance": balance,
        "trailing_rows_without_future_data": int(df["future_return"].isna().sum()),
        "source_features_manifest": str(source_manifest),
        "first_timestamp": str(df.index.min()) if len(df) else None,
        "last_timestamp": str(df.index.max()) if len(df) else None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return parquet_path, manifest_path


def add_target_for_asset_timeframe(asset_key: str, timeframe: Timeframe) -> TargetResult:
    features_df, source_manifest = find_latest_features(asset_key, timeframe)
    labeled = generate_target(features_df)
    parquet_path, manifest_path = save_labeled_features(
        labeled, asset_key, timeframe, source_manifest, TARGET.horizon_bars, TARGET.volatility_multiplier
    )
    return TargetResult(
        asset_key=asset_key,
        timeframe=timeframe.value,
        parquet_path=str(parquet_path),
        manifest_path=str(manifest_path),
        row_count=len(labeled),
        class_balance=class_balance_report(labeled),
    )


def build_all_targets(asset_keys: list[str] | None = None) -> list[dict]:
    from app.config import TIMEFRAMES

    asset_keys = asset_keys or list(ASSETS.keys())
    results: list[dict] = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            try:
                r = add_target_for_asset_timeframe(asset_key, timeframe)
                results.append(
                    {
                        "asset_key": r.asset_key,
                        "timeframe": r.timeframe,
                        "row_count": r.row_count,
                        "parquet_path": r.parquet_path,
                        "manifest_path": r.manifest_path,
                        "class_balance": r.class_balance,
                    }
                )
            except FileNotFoundError as exc:
                results.append({"asset_key": asset_key, "timeframe": timeframe.value, "error": str(exc)})
    return results


if __name__ == "__main__":
    for r in build_all_targets():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} FAILED: {r['error']}")
        else:
            pct = r["class_balance"]["percentages"]
            print(
                f"{r['asset_key']:<8} {r['timeframe']:<4} rows={r['row_count']:<7} "
                f"labeled={r['class_balance']['total_labeled_rows']:<7} "
                f"BUY={pct.get('BUY', 0):>5}% HOLD={pct.get('HOLD', 0):>5}% SELL={pct.get('SELL', 0):>5}%"
            )
