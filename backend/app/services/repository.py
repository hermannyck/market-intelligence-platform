"""Phase 13: file-backed repository layer for the API.

Everything the API serves (market data, predictions, explainability, walk-forward,
backtesting, news sentiment) already exists as files produced by Phases 2-12 — this platform
is a batch-computed research system, not a live one, so there is no need to duplicate that
data into a database just to serve it. These functions locate the latest relevant file(s) and
shape them into JSON-safe Python structures; routers stay thin, calling straight into here.

**Model performance by regime (spec Section 6) is derived from already-computed artifacts, not
recomputed per request.** Re-running walk-forward validation (retraining per window) inside an
HTTP request would make that endpoint take as long as a full Phase 8/12 batch run — instead,
`model_performance_by_regime` joins Phase 12's saved backtest trade log against the `regime`
column already sitting in `data/features/`, both cheap file reads.
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from app.config import ASSETS, ModelName
from app.explainability.pipeline import find_latest_model
from app.features.feature_engineering import find_latest_features
from app.ml.models import ALL_FEATURE_COLUMNS, MODELS as ALL_MODEL_NAMES, MODELS_DIR, TARGET_LABELS, prepare_dataset
from app.regime.detector import regime_distribution as _regime_distribution


def _latest_file(directory: Path, pattern: str) -> Path | None:
    paths = sorted(directory.glob(pattern))
    return paths[-1] if paths else None


def _df_to_records(df: pd.DataFrame, index_name: str = "timestamp") -> list[dict]:
    """NaN -> null, Timestamp -> ISO8601, via pandas' own (well-tested) JSON conversion rather
    than hand-rolled serialization."""
    df = df.reset_index()
    df = df.rename(columns={df.columns[0]: index_name})
    return json.loads(df.to_json(orient="records", date_format="iso"))


def market_analysis(asset_key: str, timeframe, limit: int = 200) -> dict:
    df, manifest_path = find_latest_features(asset_key, timeframe)
    tail = df.tail(limit)
    latest = df.iloc[-1]

    mtf_cols = ["M15_direction", "H1_direction", "H4_direction", "D1_direction", "mtf_bias"]
    mtf_bias = {col: (None if pd.isna(latest.get(col)) else latest.get(col)) for col in mtf_cols if col in df.columns}

    regime_info = None
    if "regime" in df.columns:
        regime_history = df.tail(limit)[["regime"]].dropna()
        regime_info = {
            "current_regime": None if pd.isna(latest.get("regime")) else latest.get("regime"),
            "regime_history": _df_to_records(regime_history),
            "regime_distribution": _regime_distribution(df),
        }

    return {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "current_timestamp": str(df.index[-1]),
        "current_price": float(latest["close"]),
        "bars": _df_to_records(tail),
        "multi_timeframe_bias": mtf_bias,
        "regime": regime_info,
        "source_manifest": str(manifest_path),
    }


def _predict_latest_row(asset_key: str, timeframe, model_name: ModelName) -> dict | None:
    try:
        model_path = find_latest_model(asset_key, timeframe, model_name)
    except FileNotFoundError:
        return None
    pipeline = joblib.load(model_path)

    features_df, _ = find_latest_features(asset_key, timeframe)
    dataset = prepare_dataset(features_df)
    if dataset.empty:
        return None
    latest_row = dataset.iloc[[-1]][ALL_FEATURE_COLUMNS]

    probabilities = pipeline.predict_proba(latest_row)[0]
    predicted_idx = int(probabilities.argmax())
    return {
        "model_name": model_name.value,
        "predicted_class": TARGET_LABELS[predicted_idx],
        "probabilities": {label: float(p) for label, p in zip(TARGET_LABELS, probabilities)},
        "model_path": str(model_path),
        "prediction_timestamp": str(dataset.index[-1]),
    }


def predictions_with_consensus(asset_key: str, timeframe) -> dict:
    per_model = []
    for model_name in ALL_MODEL_NAMES:
        result = _predict_latest_row(asset_key, timeframe, model_name)
        if result is not None:
            per_model.append(result)

    if not per_model:
        return {
            "asset_key": asset_key, "timeframe": timeframe.value, "predictions": [],
            "consensus_class": None, "consensus_ratio": None,
        }

    votes = [p["predicted_class"] for p in per_model]
    consensus_class = max(set(votes), key=votes.count)
    consensus_ratio = f"{votes.count(consensus_class)}/{len(votes)}"

    features_df, _ = find_latest_features(asset_key, timeframe)
    latest_price = float(features_df["close"].iloc[-1])

    return {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "timestamp": str(features_df.index[-1]),
        "price": latest_price,
        "predictions": per_model,
        "consensus_class": consensus_class,
        "consensus_ratio": consensus_ratio,
    }


def latest_explainability_report(asset_key: str, timeframe, model_name: ModelName) -> dict | None:
    path = _latest_file(MODELS_DIR, f"{asset_key}_{timeframe.value}_{model_name.value}_explainability_*.json")
    if path is None:
        return None
    return json.loads(path.read_text())


def latest_baseline_comparison(asset_key: str, timeframe) -> dict | None:
    path = _latest_file(MODELS_DIR, f"{asset_key}_{timeframe.value}_baseline_comparison_*.json")
    return json.loads(path.read_text()) if path else None


def latest_walk_forward_report(asset_key: str, timeframe) -> dict | None:
    path = _latest_file(MODELS_DIR, f"{asset_key}_{timeframe.value}_walk_forward_*.json")
    return json.loads(path.read_text()) if path else None


def model_lab(asset_key: str, timeframe) -> dict:
    return {
        "asset_key": asset_key,
        "timeframe": timeframe.value,
        "baseline_comparison": latest_baseline_comparison(asset_key, timeframe),
        "walk_forward": latest_walk_forward_report(asset_key, timeframe),
    }


def latest_backtest_report(asset_key: str, timeframe, model_name: ModelName) -> dict | None:
    path = _latest_file(MODELS_DIR, f"{asset_key}_{timeframe.value}_{model_name.value}_backtest_*.json")
    return json.loads(path.read_text()) if path else None


def model_performance_by_regime(asset_key: str, timeframe, model_name: ModelName) -> dict | None:
    backtest = latest_backtest_report(asset_key, timeframe, model_name)
    if backtest is None or not backtest["trades"]:
        return None

    features_df, _ = find_latest_features(asset_key, timeframe)
    if "regime" not in features_df.columns:
        return None

    trades_df = pd.DataFrame(backtest["trades"])
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"], utc=True)
    trades_df["regime_at_entry"] = trades_df["entry_time"].map(
        lambda ts: features_df["regime"].asof(ts) if ts >= features_df.index[0] else None
    )

    by_regime = {}
    for regime, group in trades_df.dropna(subset=["regime_at_entry"]).groupby("regime_at_entry"):
        wins = (group["net_return_pct"] > 0).sum()
        by_regime[regime] = {
            "num_trades": int(len(group)),
            "win_rate": float(wins / len(group)),
            "avg_return_pct": float(group["net_return_pct"].mean()),
        }
    return by_regime


def news_sentiment(asset_key: str, limit: int = 100) -> dict:
    from app.sentiment.pipeline import SCORED_NEWS_PATH

    if not SCORED_NEWS_PATH.exists():
        return {"asset_key": asset_key, "articles": [], "note": "No scored news available -- run app.sentiment.pipeline first."}

    scored = pd.read_parquet(SCORED_NEWS_PATH)
    asset_news = scored[scored["asset_key"] == asset_key].sort_values("published_at").tail(limit)
    articles = json.loads(
        asset_news[["published_at", "headline", "sentiment_score", "positive_prob", "negative_prob", "neutral_prob"]]
        .to_json(orient="records", date_format="iso")
    )
    return {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "articles": articles,
        "source": "Synthetic sample dataset (not real historical news) -- see data/news/README.md",
    }
