"""Phase 8: time-aware walk-forward validation (spec Section 10) — multiple expanding
train/test windows, never a random split, computing both ML metrics (accuracy, precision,
recall, F1, confusion matrix, ROC-AUC) and simplified trading-oriented metrics (win rate,
profit factor, Sharpe ratio, max drawdown, cumulative return, number of trades) per window and
in aggregate.

**Configured windows vs. auto-generated fallback windows — a real data-availability
constraint, not a design choice made lightly.** `app.config.DEFAULT_WALK_FORWARD_WINDOWS`
gives the spec's exact example (train 2021, test 2022; train 2021-2022, test 2023; ...) — this
fits D1 well (Phase 2 found decades of D1 history for all 3 assets), but M15 only has ~60-90
days of history and most of H1 only ~2 years (Phase 2/3 findings), so those 2021-2025 windows
have **zero** real data for M15 and often too little for H1. Rather than silently producing a
misleading "0 rows, 0% accuracy" result, `resolve_configured_windows` marks each configured
window `applicable` only if both its train and test slices meet a minimum row count; if *none*
of the configured windows are applicable, `generate_fallback_windows` builds an expanding-window
scheme purely from whatever date range actually has data. Every window in every report is
tagged `"source": "configured"` or `"source": "auto_generated_fallback"` so this substitution
is never hidden.

**ML performance vs. trading performance — kept explicitly distinct (spec Section 11).** The
trading metrics computed here are a *simplified, walk-forward-native diagnostic*: a BUY
prediction is treated as capturing that row's already-known `future_return` (Phase 6) as if a
full position were opened and closed with zero cost; SELL captures `-future_return`; HOLD opens
nothing. There is no transaction cost, spread, position sizing, or stop-loss/take-profit here —
that is Phase 12's job (a dedicated, realistic backtest engine). Every trading-metrics dict is
nested under `"trading"` in the report specifically so it is never confused with the
classification metrics sitting next to it.

**No leakage in using `future_return` for evaluation.** The model never sees `future_return` as
an input feature (Phase 6/7 already exclude it from `ALL_FEATURE_COLUMNS`) — it's used here only
*after* prediction, to score what a trade following that prediction would actually have
returned. Scoring a retrospective prediction against the true outcome is not leakage; feeding
the true outcome to the model as an input would be.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from app.config import ASSETS, DEFAULT_WALK_FORWARD_WINDOWS, ModelName, TIMEFRAMES, Timeframe, WalkForwardWindow
from app.features.feature_engineering import find_latest_features
from app.ml.models import (
    ALL_FEATURE_COLUMNS,
    build_pipelines,
    decode_labels,
    encode_labels,
    evaluate,
    prepare_dataset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"

MIN_ROWS_PER_SPLIT = 30


def window_slices(df: pd.DataFrame, window: WalkForwardWindow) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df.loc[window.train_start : window.train_end]
    test = df.loc[window.test_start : window.test_end]
    return train, test


def resolve_configured_windows(
    df: pd.DataFrame, windows: tuple[WalkForwardWindow, ...] | None = None, min_rows: int = MIN_ROWS_PER_SPLIT
) -> list[dict]:
    windows = windows if windows is not None else DEFAULT_WALK_FORWARD_WINDOWS
    resolved = []
    for w in windows:
        train, test = window_slices(df, w)
        applicable = len(train) >= min_rows and len(test) >= min_rows
        resolved.append(
            {"window": w, "train_rows": len(train), "test_rows": len(test), "applicable": applicable, "source": "configured"}
        )
    return resolved


def generate_fallback_windows(
    df: pd.DataFrame, n_windows: int = 4, min_rows: int = MIN_ROWS_PER_SPLIT
) -> list[dict]:
    """Expanding-window scheme purely from data availability (see module docstring). Splits
    the available rows into n_windows+1 equal-sized chronological chunks: window i trains on
    chunks[0..i] and tests on chunk[i+1] -- the same expanding-train/sliding-test shape as the
    spec's calendar-date example, just sized to whatever history actually exists."""
    n = len(df)
    chunk_size = n // (n_windows + 1)
    if chunk_size < min_rows:
        return []

    resolved = []
    for i in range(n_windows):
        train_end_idx = (i + 1) * chunk_size
        test_end_idx = (i + 2) * chunk_size if i < n_windows - 1 else n
        train = df.iloc[:train_end_idx]
        test = df.iloc[train_end_idx:test_end_idx]
        if len(train) < min_rows or len(test) < min_rows:
            continue
        window = WalkForwardWindow(
            train_start=str(train.index.min()),
            train_end=str(train.index.max()),
            test_start=str(test.index.min()),
            test_end=str(test.index.max()),
        )
        resolved.append(
            {"window": window, "train_rows": len(train), "test_rows": len(test), "applicable": True, "source": "auto_generated_fallback"}
        )
    return resolved


def resolve_windows(df: pd.DataFrame, windows: tuple[WalkForwardWindow, ...] | None = None) -> list[dict]:
    configured = resolve_configured_windows(df, windows)
    applicable = [w for w in configured if w["applicable"]]
    if applicable:
        return applicable
    return generate_fallback_windows(df)


def compute_trading_metrics(y_pred_labels: np.ndarray, future_returns: np.ndarray) -> dict:
    """Simplified per-window trading diagnostic -- see module docstring for exactly what this
    does and doesn't model. Not the Phase 12 backtest engine."""
    direction = np.where(y_pred_labels == "BUY", 1, np.where(y_pred_labels == "SELL", -1, 0))
    trade_mask = direction != 0
    trade_returns = direction[trade_mask] * future_returns[trade_mask]
    trade_returns = trade_returns[~np.isnan(trade_returns)]

    n_trades = int(len(trade_returns))
    if n_trades == 0:
        return {
            "num_trades": 0, "win_rate": None, "profit_factor": None,
            "sharpe_ratio": None, "max_drawdown": None, "cumulative_return": None,
        }

    wins = trade_returns[trade_returns > 0]
    losses = trade_returns[trade_returns < 0]
    win_rate = len(wins) / n_trades

    if len(losses) > 0 and losses.sum() != 0:
        profit_factor: float | None = float(wins.sum() / abs(losses.sum()))
    elif wins.sum() > 0:
        profit_factor = None  # undefined (no losing trades to divide by) rather than a fake "infinity"
    else:
        profit_factor = 0.0

    sharpe_ratio = float(trade_returns.mean() / trade_returns.std()) if trade_returns.std() > 0 else None

    equity = np.cumprod(1 + trade_returns)
    running_max = np.maximum.accumulate(equity)
    drawdown = (equity - running_max) / running_max
    max_drawdown = float(drawdown.min())
    cumulative_return = float(equity[-1] - 1)

    return {
        "num_trades": n_trades,
        "win_rate": float(win_rate),
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "max_drawdown": max_drawdown,
        "cumulative_return": cumulative_return,
    }


def evaluate_with_roc_auc(pipeline, X_test: pd.DataFrame, y_test_encoded: np.ndarray) -> dict:
    metrics = evaluate(pipeline, X_test, y_test_encoded)
    try:
        y_proba = pipeline.predict_proba(X_test)
        metrics["roc_auc_macro"] = float(
            roc_auc_score(y_test_encoded, y_proba, multi_class="ovr", average="macro", labels=[0, 1, 2])
        )
    except ValueError:
        # e.g. a class is entirely absent from this window's (small) test slice -- ROC-AUC
        # isn't well-defined then. "where appropriate" per spec Section 10; None, not a crash.
        metrics["roc_auc_macro"] = None
    return metrics


def run_window(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    X_train, y_train = train[ALL_FEATURE_COLUMNS], encode_labels(train["target"])
    X_test, y_test = test[ALL_FEATURE_COLUMNS], encode_labels(test["target"])
    future_returns_test = test["future_return"].to_numpy()

    per_model = {}
    for model_name, pipeline in build_pipelines().items():
        pipeline.fit(X_train, y_train)
        metrics = evaluate_with_roc_auc(pipeline, X_test, y_test)
        y_pred_labels = decode_labels(pipeline.predict(X_test))
        metrics["trading"] = compute_trading_metrics(y_pred_labels, future_returns_test)
        per_model[model_name.value] = metrics
    return per_model


def aggregate_across_windows(per_window_results: list[dict]) -> dict:
    """Mean/std of each metric across windows, per model. The std is a direct stability
    measure (spec Section 21 RQ8: can predictions stay reasonably stable across different
    historical periods?), not just a summary statistic."""
    if not per_window_results:
        return {}
    model_names = per_window_results[0]["models"].keys()
    overall = {}
    for model_name in model_names:
        values_by_metric: dict[str, list[float]] = {}
        for w in per_window_results:
            m = w["models"][model_name]
            for key in ("accuracy", "precision_macro", "recall_macro", "f1_macro", "roc_auc_macro"):
                v = m.get(key)
                if v is not None:
                    values_by_metric.setdefault(key, []).append(v)
            for key in ("win_rate", "profit_factor", "sharpe_ratio", "max_drawdown", "cumulative_return"):
                v = m.get("trading", {}).get(key)
                if v is not None and np.isfinite(v):
                    values_by_metric.setdefault(f"trading_{key}", []).append(v)
        overall[model_name] = {
            **{f"{k}_mean": float(np.mean(vs)) for k, vs in values_by_metric.items()},
            **{f"{k}_std": float(np.std(vs)) for k, vs in values_by_metric.items()},
            **{f"{k}_n_windows": len(vs) for k, vs in values_by_metric.items()},
        }
    return overall


def save_walk_forward_report(
    asset_key: str,
    timeframe: Timeframe,
    per_window_results: list[dict],
    overall: dict,
    source_manifest: Path,
    n_configured_windows: int,
    n_resolved_windows: int,
    window_source: str,
) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = MODELS_DIR / f"{asset_key}_{timeframe.value}_walk_forward_{stamp}.json"
    if path.exists():
        raise FileExistsError(f"{path} already exists; refusing to overwrite a walk-forward report.")

    report = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "n_configured_windows": n_configured_windows,
        "n_resolved_windows": n_resolved_windows,
        "window_source": window_source,
        "source_features_manifest": str(source_manifest),
        "windows": per_window_results,
        "overall": overall,
    }
    path.write_text(json.dumps(report, indent=2))
    return path


def generate_oos_predictions(asset_key: str, timeframe: Timeframe, model_name: ModelName) -> pd.Series:
    """Out-of-sample predictions across every resolved walk-forward window, for one model.
    Each test-period prediction comes from a Pipeline trained ONLY on that window's prior
    training data -- exactly "predictions generated from information available at that time"
    (spec Section 11), which is what Phase 12's backtest engine needs as its input instead of
    the true `target` label. Concatenated across windows, indexed by timestamp; bars not
    covered by any resolved window's test period (e.g. the very first window's whole training
    span) are simply absent, not backfilled with anything.
    """
    features_df, _ = find_latest_features(asset_key, timeframe)
    dataset = prepare_dataset(features_df)
    resolved = resolve_windows(dataset)

    predictions = []
    for w in resolved:
        train, test = window_slices(dataset, w["window"])
        X_train, y_train = train[ALL_FEATURE_COLUMNS], encode_labels(train["target"])
        pipeline = build_pipelines()[model_name]
        pipeline.fit(X_train, y_train)
        y_pred = decode_labels(pipeline.predict(test[ALL_FEATURE_COLUMNS]))
        predictions.append(pd.Series(y_pred, index=test.index))

    if not predictions:
        return pd.Series(dtype=object)
    combined = pd.concat(predictions).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def run_walk_forward(asset_key: str, timeframe: Timeframe) -> dict:
    features_df, source_manifest = find_latest_features(asset_key, timeframe)
    dataset = prepare_dataset(features_df)

    resolved = resolve_windows(dataset)
    window_source = resolved[0]["source"] if resolved else "none"

    per_window_results = []
    for w in resolved:
        train, test = window_slices(dataset, w["window"])
        per_model = run_window(train, test)
        per_window_results.append(
            {
                "window": asdict(w["window"]),
                "source": w["source"],
                "train_rows": len(train),
                "test_rows": len(test),
                "models": per_model,
            }
        )

    overall = aggregate_across_windows(per_window_results)
    configured = resolve_configured_windows(dataset)
    report_path = save_walk_forward_report(
        asset_key, timeframe, per_window_results, overall, source_manifest,
        n_configured_windows=sum(1 for w in configured if w["applicable"]),
        n_resolved_windows=len(resolved),
        window_source=window_source,
    )
    return {
        "asset_key": asset_key,
        "timeframe": timeframe.value,
        "n_windows": len(resolved),
        "window_source": window_source,
        "report_path": str(report_path),
        "overall": overall,
    }


def run_all_walk_forward(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    results = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            try:
                results.append(run_walk_forward(asset_key, timeframe))
            except (FileNotFoundError, ValueError) as exc:
                results.append({"asset_key": asset_key, "timeframe": timeframe.value, "error": str(exc)})
    return results


if __name__ == "__main__":
    for r in run_all_walk_forward():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} FAILED: {r['error']}")
        elif r["n_windows"] == 0:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} SKIPPED: not enough data for any window")
        else:
            acc = {m: v.get("accuracy_mean") for m, v in r["overall"].items()}
            print(
                f"{r['asset_key']:<8} {r['timeframe']:<4} windows={r['n_windows']} ({r['window_source']}) "
                + " ".join(f"{m}={a:.3f}" if a is not None else f"{m}=n/a" for m, a in acc.items())
            )
