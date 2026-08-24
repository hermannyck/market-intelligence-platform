"""Phase 11: SHAP explainability (spec Section 12).

**Explainer choice per model**, matched to what SHAP supports well and to the spec's own
guidance ("for tree-based models... use appropriate SHAP explainers"):

- Random Forest, XGBoost: `shap.TreeExplainer` — exact, fast.
- Logistic Regression: `shap.LinearExplainer` — exact for a linear model.
- SVM (RBF kernel — no linear/tree structure): `shap.KernelExplainer`, the model-agnostic
  fallback. Empirically ~3s/explained row even with a small k-means-summarized background
  (20 points) — `app.config.EXPLAIN` caps both the background size and how many rows get a
  KernelExplainer explanation per run, a deliberate, documented cost trade-off, not a
  correctness shortcut (every explained row still gets a real SHAP computation).

**All four explainers were empirically verified (shap 0.52.0) to return SHAP values as one
consistent `(n_samples, n_features, n_classes)` array** with a matching `(n_classes,)`
`expected_value` — so no per-model special-casing is needed for the *output* shape, only for
explainer *construction* (`build_explainer`).

**One-hot aggregation.** Every explainer operates on the pipeline's *preprocessed* feature
space (post-`ColumnTransformer`: scaled/passthrough numeric columns + one-hot-encoded
categoricals), since that's the actual input the classifier sees. SHAP values are additive, so
`aggregate_shap_to_original_features` sums the one-hot dummy columns belonging to the same
original categorical feature (e.g. all `categorical__H1_direction_*` columns) back into one
`H1_direction` contribution — the standard technique for keeping one-hot-encoded feature
explanations readable, and consistent with the feature names used everywhere else in this
project rather than exploded dummy columns.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap
from sklearn.pipeline import Pipeline

from app.config import EXPLAIN, ModelName
from app.ml.models import CATEGORICAL_FEATURE_COLUMNS, TARGET_LABELS


def _split_pipeline(pipeline: Pipeline):
    return pipeline.named_steps["preprocess"], pipeline.named_steps["clf"]


def _transform(preprocessor, X: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    transformed = preprocessor.transform(X)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    return np.asarray(transformed, dtype=float), list(preprocessor.get_feature_names_out())


def original_feature_name(transformed_name: str) -> str:
    """"numeric__EMA20" -> "EMA20"; "categorical__H1_direction_BULLISH" -> "H1_direction"."""
    if transformed_name.startswith("numeric__"):
        return transformed_name[len("numeric__") :]
    if transformed_name.startswith("categorical__"):
        rest = transformed_name[len("categorical__") :]
        for base_col in CATEGORICAL_FEATURE_COLUMNS:
            if rest.startswith(base_col):
                return base_col
        raise ValueError(f"Could not map {transformed_name!r} to a known categorical column.")
    raise ValueError(f"Unrecognized preprocessed feature name: {transformed_name!r}")


def build_explainer(pipeline: Pipeline, model_name: ModelName, background_df: pd.DataFrame):
    """Returns (explainer, transformed_feature_names)."""
    preprocessor, clf = _split_pipeline(pipeline)
    background_transformed, feature_names = _transform(preprocessor, background_df)

    if model_name in (ModelName.RANDOM_FOREST, ModelName.XGBOOST):
        explainer = shap.TreeExplainer(clf)
    elif model_name == ModelName.LOGISTIC_REGRESSION:
        explainer = shap.LinearExplainer(clf, background_transformed)
    elif model_name == ModelName.SVM:
        n_bg = min(EXPLAIN.kernel_explainer_background_size, len(background_transformed))
        background_summary = shap.kmeans(background_transformed, n_bg)
        explainer = shap.KernelExplainer(clf.predict_proba, background_summary)
    else:
        raise ValueError(f"No SHAP explainer strategy defined for {model_name}.")
    return explainer, feature_names


def compute_shap_values(
    pipeline: Pipeline, model_name: ModelName, X: pd.DataFrame, background_df: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Returns (shap_values, expected_value, transformed_feature_names).
    shap_values: (n_samples, n_transformed_features, n_classes). expected_value: (n_classes,).
    For SVM, `X` is capped to `EXPLAIN.kernel_explainer_sample_size` rows before scoring —
    KernelExplainer is expensive enough that explaining an unbounded number of rows isn't
    practical; callers that need more should chunk their own calls."""
    preprocessor, _ = _split_pipeline(pipeline)
    explainer, feature_names = build_explainer(pipeline, model_name, background_df)
    X_transformed, _ = _transform(preprocessor, X)

    if model_name == ModelName.SVM:
        n = min(len(X_transformed), EXPLAIN.kernel_explainer_sample_size)
        X_transformed = X_transformed[:n]
        shap_values = explainer.shap_values(X_transformed, nsamples=EXPLAIN.kernel_explainer_nsamples)
    else:
        shap_values = explainer.shap_values(X_transformed)

    return np.asarray(shap_values, dtype=float), np.asarray(explainer.expected_value, dtype=float), feature_names


def aggregate_shap_to_original_features(
    shap_values: np.ndarray, transformed_feature_names: list[str]
) -> tuple[np.ndarray, list[str]]:
    """Sums one-hot dummy columns back onto their original feature (SHAP values are additive,
    so this is exact, not an approximation). Returns (aggregated_shap_values, original_names)
    where aggregated_shap_values has shape (n_samples, n_original_features, n_classes)."""
    original_names_per_col = [original_feature_name(n) for n in transformed_feature_names]
    unique_names = list(dict.fromkeys(original_names_per_col))  # de-dup, preserve first-seen order

    n_samples, _, n_classes = shap_values.shape
    aggregated = np.zeros((n_samples, len(unique_names), n_classes))
    for new_idx, name in enumerate(unique_names):
        cols = [i for i, n in enumerate(original_names_per_col) if n == name]
        aggregated[:, new_idx, :] = shap_values[:, cols, :].sum(axis=1)
    return aggregated, unique_names


def global_feature_importance(aggregated_shap_values: np.ndarray, original_feature_names: list[str]) -> pd.Series:
    """Mean absolute SHAP value per feature, averaged over samples AND classes -- a single
    overall importance ranking ("which features are most important overall", spec Section 12).
    """
    mean_abs = np.abs(aggregated_shap_values).mean(axis=(0, 2))
    return pd.Series(mean_abs, index=original_feature_names).sort_values(ascending=False)


def local_explanation(
    aggregated_shap_row: np.ndarray,
    original_feature_names: list[str],
    expected_value: np.ndarray,
    probabilities: np.ndarray,
    predicted_class_idx: int,
    top_n: int | None = None,
) -> dict:
    """Formats one row's explanation matching spec Section 12's example: predicted class,
    per-class probabilities, and the top-N features by signed SHAP contribution for the
    PREDICTED class -- "why did the model produce this particular prediction"."""
    top_n = EXPLAIN.top_n_local_factors if top_n is None else top_n
    class_shap = aggregated_shap_row[:, predicted_class_idx]
    order = np.argsort(-np.abs(class_shap))[:top_n]
    top_factors = [
        {"feature": original_feature_names[i], "shap_value": float(class_shap[i])} for i in order
    ]
    return {
        "predicted_class": TARGET_LABELS[predicted_class_idx],
        "probabilities": {label: float(p) for label, p in zip(TARGET_LABELS, probabilities)},
        "top_factors": top_factors,
        "base_value_for_predicted_class": float(expected_value[predicted_class_idx]),
    }
