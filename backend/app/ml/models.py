"""Phase 7: baseline ML models (spec Section 8) — Logistic Regression, Random Forest, SVM,
XGBoost, each as a single sklearn Pipeline (preprocessing + classifier fused into one
fit/predict object, per the spec's "use Pipelines to prevent preprocessing leakage"
requirement).

**Baseline, not walk-forward.** This is a single chronological train/test split — the first
`TRAIN_FRACTION` of rows (by time order) train, the rest test. **Never a random shuffle** of
time-series data (spec Section 8's explicit prohibition). Full expanding-window walk-forward
validation across multiple windows is Phase 8; this phase establishes the model pipelines and
a first honest read on relative performance.

**Preprocessing that respects the leakage boundary.** `StandardScaler` lives *inside* each
Pipeline, so it is fit only when `.fit(X_train, ...)` is called — never on the test split,
never on the full dataset. Categorical multi-timeframe direction columns are one-hot encoded
for every model (tree models don't need scaling, but do need the categoricals turned into
numbers same as everyone else).

**Why categorical NaN becomes "UNKNOWN" instead of dropping the row.** Phase 5 documented that
`M15_direction`/`H1_direction` are NaN for most of D1's multi-year history (M15/H1 only have
~60-90 days / ~2 years of data). Dropping every row with *any* NaN feature would throw away
almost all of D1's usable history over one column that's structurally unavailable that far
back. Converting NaN to the literal string "UNKNOWN" (one-hot encoded like any other category)
keeps the row while being explicit that the model is told "not known" rather than fed a
fabricated guess. Numeric feature NaNs (indicator/derived-feature warmup, Phase 4/5; missing
target, Phase 6) are still hard-dropped — there's no honest categorical-style placeholder for
a missing EMA200 value.

**Label encoding.** XGBoost's sklearn API requires integer class labels (rejects strings
outright); to keep all four models on identical footing rather than special-casing one, every
model here is fit on the same integer-encoded labels via the fixed `TARGET_LABELS` order, and
predictions are decoded back to BUY/HOLD/SELL strings before any metric or report is produced.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC
from xgboost import XGBClassifier

from app.config import ASSETS, MODELS, TIMEFRAMES, ModelName, Timeframe
from app.features.derived import DERIVED_COLUMNS
from app.features.feature_engineering import FEATURES_DIR, find_latest_features
from app.features.indicators import INDICATOR_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"

NUMERIC_FEATURE_COLUMNS: list[str] = list(INDICATOR_COLUMNS) + list(DERIVED_COLUMNS)
CATEGORICAL_FEATURE_COLUMNS: list[str] = [f"{tf.value}_direction" for tf in TIMEFRAMES] + ["mtf_bias"]
ALL_FEATURE_COLUMNS: list[str] = NUMERIC_FEATURE_COLUMNS + CATEGORICAL_FEATURE_COLUMNS

TRAIN_FRACTION = 0.8

# Fixed order so every model (including XGBoost, which requires integers) is trained/evaluated
# on an identical encoding.
TARGET_LABELS: list[str] = ["SELL", "HOLD", "BUY"]
_LABEL_TO_INT = {label: i for i, label in enumerate(TARGET_LABELS)}
_INT_TO_LABEL = {i: label for label, i in _LABEL_TO_INT.items()}


def encode_labels(y: pd.Series) -> np.ndarray:
    return y.map(_LABEL_TO_INT).to_numpy()


def decode_labels(y_encoded: np.ndarray) -> np.ndarray:
    return np.array([_INT_TO_LABEL[int(v)] for v in y_encoded])


def prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Categorical NaN -> "UNKNOWN" (kept). Numeric feature NaN or missing target -> row
    dropped (no honest placeholder exists for a missing indicator value)."""
    df = df.copy()
    for col in CATEGORICAL_FEATURE_COLUMNS:
        df[col] = df[col].fillna("UNKNOWN").astype(str)
    df = df.dropna(subset=NUMERIC_FEATURE_COLUMNS + ["target"])
    return df


def chronological_split(
    df: pd.DataFrame, train_fraction: float = TRAIN_FRACTION
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """First `train_fraction` of rows (already time-sorted) -> train, remainder -> test.
    Never a random shuffle -- spec Section 8's explicit requirement for time-series data."""
    if not df.index.is_monotonic_increasing:
        raise ValueError("Input must be sorted ascending by timestamp before splitting.")
    split_idx = int(len(df) * train_fraction)
    return df.iloc[:split_idx], df.iloc[split_idx:]


def _preprocessor(scale_numeric: bool) -> ColumnTransformer:
    numeric_step = StandardScaler() if scale_numeric else "passthrough"
    return ColumnTransformer(
        [
            ("numeric", numeric_step, NUMERIC_FEATURE_COLUMNS),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURE_COLUMNS),
        ]
    )


def build_pipelines(random_state: int = 42) -> dict[ModelName, Pipeline]:
    """One Pipeline per spec-mandated model. Scaling only for the two scale-sensitive models
    (Logistic Regression, SVM); Random Forest and XGBoost are scale-invariant by construction
    so scaling them would add cost without benefit."""
    return {
        ModelName.LOGISTIC_REGRESSION: Pipeline(
            [
                ("preprocess", _preprocessor(scale_numeric=True)),
                ("clf", LogisticRegression(max_iter=1000, random_state=random_state)),
            ]
        ),
        ModelName.RANDOM_FOREST: Pipeline(
            [
                ("preprocess", _preprocessor(scale_numeric=False)),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=200, max_depth=10, random_state=random_state, n_jobs=-1
                    ),
                ),
            ]
        ),
        ModelName.SVM: Pipeline(
            [
                ("preprocess", _preprocessor(scale_numeric=True)),
                ("clf", SVC(probability=True, random_state=random_state)),
            ]
        ),
        ModelName.XGBOOST: Pipeline(
            [
                ("preprocess", _preprocessor(scale_numeric=False)),
                (
                    "clf",
                    XGBClassifier(
                        n_estimators=200,
                        max_depth=6,
                        random_state=random_state,
                        eval_metric="mlogloss",
                    ),
                ),
            ]
        ),
    }


def evaluate(pipeline: Pipeline, X_test: pd.DataFrame, y_test_encoded: np.ndarray) -> dict:
    y_pred_encoded = pipeline.predict(X_test)
    y_test_labels = decode_labels(y_test_encoded)
    y_pred_labels = decode_labels(y_pred_encoded)

    accuracy = float((y_pred_encoded == y_test_encoded).mean())
    precision_macro, recall_macro, f1_macro, _ = precision_recall_fscore_support(
        y_test_labels, y_pred_labels, labels=TARGET_LABELS, average="macro", zero_division=0
    )
    precision_weighted, recall_weighted, f1_weighted, _ = precision_recall_fscore_support(
        y_test_labels, y_pred_labels, labels=TARGET_LABELS, average="weighted", zero_division=0
    )
    cm = confusion_matrix(y_test_labels, y_pred_labels, labels=TARGET_LABELS).tolist()

    return {
        "accuracy": accuracy,
        "precision_macro": float(precision_macro),
        "recall_macro": float(recall_macro),
        "f1_macro": float(f1_macro),
        "precision_weighted": float(precision_weighted),
        "recall_weighted": float(recall_weighted),
        "f1_weighted": float(f1_weighted),
        "confusion_matrix": cm,
        "confusion_matrix_labels": TARGET_LABELS,
    }


def save_model(pipeline: Pipeline, asset_key: str, timeframe: Timeframe, model_name: ModelName) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = MODELS_DIR / f"{asset_key}_{timeframe.value}_{model_name.value}_{stamp}.joblib"
    if path.exists():
        raise FileExistsError(f"{path} already exists; refusing to overwrite a trained model.")
    joblib.dump(pipeline, path)
    return path


@dataclass
class BaselineTrainingResult:
    asset_key: str
    timeframe: str
    train_rows: int
    test_rows: int
    per_model: dict[str, dict]
    report_path: str


def train_baseline_models(asset_key: str, timeframe: Timeframe) -> BaselineTrainingResult:
    features_df, source_manifest = find_latest_features(asset_key, timeframe)
    dataset = prepare_dataset(features_df)
    train_df, test_df = chronological_split(dataset)

    X_train, y_train = train_df[ALL_FEATURE_COLUMNS], encode_labels(train_df["target"])
    X_test, y_test = test_df[ALL_FEATURE_COLUMNS], encode_labels(test_df["target"])

    per_model: dict[str, dict] = {}
    for model_name, pipeline in build_pipelines().items():
        pipeline.fit(X_train, y_train)
        metrics = evaluate(pipeline, X_test, y_test)
        model_path = save_model(pipeline, asset_key, timeframe, model_name)
        per_model[model_name.value] = {**metrics, "model_path": str(model_path)}

    report_path = save_comparison_report(
        asset_key, timeframe, per_model, len(train_df), len(test_df), source_manifest
    )
    return BaselineTrainingResult(
        asset_key=asset_key,
        timeframe=timeframe.value,
        train_rows=len(train_df),
        test_rows=len(test_df),
        per_model=per_model,
        report_path=str(report_path),
    )


def save_comparison_report(
    asset_key: str,
    timeframe: Timeframe,
    per_model: dict[str, dict],
    train_rows: int,
    test_rows: int,
    source_manifest: Path,
) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = MODELS_DIR / f"{asset_key}_{timeframe.value}_baseline_comparison_{stamp}.json"
    if path.exists():
        raise FileExistsError(f"{path} already exists; refusing to overwrite a comparison report.")

    report = {
        "asset_key": asset_key,
        "asset_code": ASSETS[asset_key].code,
        "timeframe": timeframe.value,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "split_method": "chronological (no shuffle)",
        "train_fraction": TRAIN_FRACTION,
        "train_rows": train_rows,
        "test_rows": test_rows,
        "source_features_manifest": str(source_manifest),
        "feature_columns": {"numeric": NUMERIC_FEATURE_COLUMNS, "categorical": CATEGORICAL_FEATURE_COLUMNS},
        "models": per_model,
    }
    path.write_text(json.dumps(report, indent=2))
    return path


def train_all_baseline_models(asset_keys: list[str] | None = None) -> list[dict]:
    asset_keys = asset_keys or list(ASSETS.keys())
    results = []
    for asset_key in asset_keys:
        for timeframe in TIMEFRAMES:
            try:
                r = train_baseline_models(asset_key, timeframe)
                results.append(
                    {
                        "asset_key": r.asset_key,
                        "timeframe": r.timeframe,
                        "train_rows": r.train_rows,
                        "test_rows": r.test_rows,
                        "report_path": r.report_path,
                        "accuracy_by_model": {m: v["accuracy"] for m, v in r.per_model.items()},
                    }
                )
            except (FileNotFoundError, ValueError) as exc:
                results.append({"asset_key": asset_key, "timeframe": timeframe.value, "error": str(exc)})
    return results


if __name__ == "__main__":
    for r in train_all_baseline_models():
        if "error" in r:
            print(f"{r['asset_key']:<8} {r['timeframe']:<4} FAILED: {r['error']}")
        else:
            acc = r["accuracy_by_model"]
            print(
                f"{r['asset_key']:<8} {r['timeframe']:<4} train={r['train_rows']:<6} test={r['test_rows']:<6} "
                + " ".join(f"{m}={a:.3f}" for m, a in acc.items())
            )
