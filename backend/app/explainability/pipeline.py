"""Phase 11 orchestration: load a trained model (Phase 7/8 artifact) + its labeled feature
dataset, compute a global explanation (sampled rows) and a local explanation (the most recent
row), and save both to `models/` -- same never-overwrite convention as every prior phase.

Background/explain-sample selection needs no special leakage treatment here: this is a
post-hoc analysis of an ALREADY TRAINED model (nothing is being fit on this data), so there is
no train/test boundary to respect the way Phase 7/8 does -- SHAP's "background" is just a
reference distribution for computing marginal contributions, not a training set.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.config import ASSETS, EXPLAIN, ModelName, Timeframe
from app.explainability.shap_explainer import (
    aggregate_shap_to_original_features,
    compute_shap_values,
    global_feature_importance,
    local_explanation,
)
from app.features.feature_engineering import find_latest_features
from app.ml.models import ALL_FEATURE_COLUMNS, MODELS_DIR, prepare_dataset

BACKGROUND_SAMPLE_SIZE = 200
BACKGROUND_RANDOM_STATE = 42


def find_latest_model(asset_key: str, timeframe: Timeframe, model_name: ModelName) -> Path:
    paths = sorted(MODELS_DIR.glob(f"{asset_key}_{timeframe.value}_{model_name.value}_*.joblib"))
    if not paths:
        raise FileNotFoundError(
            f"No trained {model_name.value} model for {asset_key} {timeframe.value} in {MODELS_DIR}. "
            "Run `python -m app.ml.models` first."
        )
    return paths[-1]


def _select_background_and_sample(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_bg = min(BACKGROUND_SAMPLE_SIZE, len(dataset))
    background_df = dataset.sample(n=n_bg, random_state=BACKGROUND_RANDOM_STATE)[ALL_FEATURE_COLUMNS]
    n_global = min(EXPLAIN.global_explanation_sample_size, len(dataset))
    global_sample_df = dataset.iloc[-n_global:][ALL_FEATURE_COLUMNS]
    return background_df, global_sample_df


@dataclass
class ExplainabilityResult:
    asset_key: str
    timeframe: str
    model_name: str
    report_path: str
    global_top_features: list[str]


def save_explanation_report(
    asset_key: str,
    timeframe: Timeframe,
    model_name: ModelName,
    global_importance: pd.Series,
    local_explanations: list[dict],
    source_manifest: Path,
    source_model_path: Path,
) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = MODELS_DIR / f"{asset_key}_{timeframe.value}_{model_name.value}_explainability_{stamp}.json"
    if path.exists():
        raise FileExistsError(f"{path} already exists; refusing to overwrite an explainability report.")

    report = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "model_name": model_name.value,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_model_path": str(source_model_path),
        "source_features_manifest": str(source_manifest),
        "global_feature_importance": global_importance.to_dict(),
        "local_explanations": local_explanations,
    }
    path.write_text(json.dumps(report, indent=2))
    return path


def explain_asset_timeframe_model(asset_key: str, timeframe: Timeframe, model_name: ModelName) -> ExplainabilityResult:
    model_path = find_latest_model(asset_key, timeframe, model_name)
    pipeline = joblib.load(model_path)

    features_df, source_manifest = find_latest_features(asset_key, timeframe)
    dataset = prepare_dataset(features_df)
    background_df, global_sample_df = _select_background_and_sample(dataset)

    shap_values, expected_value, transformed_names = compute_shap_values(
        pipeline, model_name, global_sample_df, background_df
    )
    aggregated, original_names = aggregate_shap_to_original_features(shap_values, transformed_names)
    global_importance = global_feature_importance(aggregated, original_names)

    # Local explanation for the single most recent row actually explained (for SVM,
    # compute_shap_values caps the explained sample -- the "most recent" row within that cap
    # is its last row, since global_sample_df itself is already time-ordered ascending and the
    # cap keeps a PREFIX of it, i.e. the *oldest* rows of the sample; to keep "local = most
    # recent" true for every model, explain the true latest row explicitly instead).
    latest_row_df = dataset.iloc[[-1]][ALL_FEATURE_COLUMNS]
    latest_shap, latest_expected, latest_names = compute_shap_values(pipeline, model_name, latest_row_df, background_df)
    latest_aggregated, latest_original_names = aggregate_shap_to_original_features(latest_shap, latest_names)

    probabilities = pipeline.predict_proba(latest_row_df)[0]
    predicted_class_idx = int(np.argmax(probabilities))
    local = local_explanation(
        latest_aggregated[0], latest_original_names, latest_expected, probabilities, predicted_class_idx
    )
    local["timestamp"] = str(dataset.index[-1])

    report_path = save_explanation_report(
        asset_key, timeframe, model_name, global_importance, [local], source_manifest, model_path
    )
    return ExplainabilityResult(
        asset_key=asset_key,
        timeframe=timeframe.value,
        model_name=model_name.value,
        report_path=str(report_path),
        global_top_features=list(global_importance.head(5).index),
    )


def explain_all(asset_keys: list[str] | None = None) -> list[dict]:
    from app.config import MODELS as ALL_MODEL_NAMES
    from app.config import TIMEFRAMES

    asset_keys = asset_keys or list(ASSETS.keys())
    results = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            for model_name in ALL_MODEL_NAMES:
                try:
                    r = explain_asset_timeframe_model(asset_key, timeframe, model_name)
                    results.append(
                        {
                            "asset_key": r.asset_key,
                            "timeframe": r.timeframe,
                            "model_name": r.model_name,
                            "report_path": r.report_path,
                            "global_top_features": r.global_top_features,
                        }
                    )
                except (FileNotFoundError, ValueError) as exc:
                    results.append(
                        {
                            "asset_key": asset_key,
                            "timeframe": timeframe.value,
                            "model_name": model_name.value,
                            "error": str(exc),
                        }
                    )
    return results


if __name__ == "__main__":
    for r in explain_all():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} {r['model_name']:<20} FAILED: {r['error']}")
        else:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} {r['model_name']:<20} top5={r['global_top_features']}")
