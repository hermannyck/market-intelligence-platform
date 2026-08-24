"""Phase 11 tests for app.explainability.shap_explainer.

Pure-logic tests (aggregation, ranking, formatting) run against small hand-crafted arrays and
are fast. test_build_explainer_and_compute_shap_values_for_each_model actually exercises the
real shap library against tiny real trained pipelines for all 4 models -- marked slow since it
includes SVM's KernelExplainer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import ModelName
from app.explainability import shap_explainer as se
from app.ml import models as ml_models


def test_original_feature_name_numeric_and_categorical():
    assert se.original_feature_name("numeric__EMA20") == "EMA20"
    assert se.original_feature_name("categorical__H1_direction_BULLISH") == "H1_direction"
    assert se.original_feature_name("categorical__mtf_bias_MIXED") == "mtf_bias"


def test_original_feature_name_unrecognized_raises():
    with pytest.raises(ValueError, match="Unrecognized"):
        se.original_feature_name("something_else__x")
    with pytest.raises(ValueError, match="Could not map"):
        se.original_feature_name("categorical__not_a_known_column_X")


def test_aggregate_shap_to_original_features_sums_one_hot_columns():
    # 1 sample, 2 classes, columns: numeric__A, categorical__C_x, categorical__C_y
    shap_values = np.array([[[1.0, -1.0], [2.0, 0.5], [3.0, 0.5]]])  # shape (1, 3, 2)
    names = ["numeric__A", "categorical__C_x", "categorical__C_y"]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(se, "CATEGORICAL_FEATURE_COLUMNS", ["C"])
        aggregated, original_names = se.aggregate_shap_to_original_features(shap_values, names)

    assert original_names == ["A", "C"]
    # class 0: A=1.0, C = 2.0+3.0 = 5.0 ; class 1: A=-1.0, C = 0.5+0.5 = 1.0
    np.testing.assert_allclose(aggregated[0], [[1.0, -1.0], [5.0, 1.0]])


def test_global_feature_importance_ranks_by_mean_abs_over_samples_and_classes():
    # shape (2 samples, 2 features, 2 classes)
    aggregated = np.array(
        [
            [[1.0, -1.0], [0.1, 0.1]],
            [[2.0, -2.0], [-0.1, 0.1]],
        ]
    )
    result = se.global_feature_importance(aggregated, ["big_feature", "small_feature"])
    assert list(result.index) == ["big_feature", "small_feature"]
    assert result["big_feature"] == pytest.approx((1 + 1 + 2 + 2) / 4)
    assert result["small_feature"] == pytest.approx((0.1 + 0.1 + 0.1 + 0.1) / 4)


def test_local_explanation_format_sign_and_top_n():
    # 4 features, 3 classes; predicted class = index 2 ("BUY")
    aggregated_row = np.array(
        [
            [0.01, 0.01, 0.21],   # RSI14-like: strong positive contribution to class 2
            [0.02, 0.02, -0.16],  # negative contribution to class 2
            [0.0, 0.0, 0.05],
            [0.0, 0.0, 0.30],     # largest positive contribution to class 2
        ]
    )
    names = ["RSI14", "ATR14", "BB_position", "MACD"]
    expected_value = np.array([0.1, 0.2, 0.3])
    probabilities = np.array([0.1, 0.18, 0.72])

    result = se.local_explanation(aggregated_row, names, expected_value, probabilities, predicted_class_idx=2, top_n=3)

    assert result["predicted_class"] == "BUY"
    assert result["probabilities"] == {"SELL": 0.1, "HOLD": 0.18, "BUY": 0.72}
    assert result["base_value_for_predicted_class"] == pytest.approx(0.3)
    assert len(result["top_factors"]) == 3
    # sorted by |shap_value| descending -> MACD (0.30), RSI14 (0.21), ATR14 (-0.16)
    assert [f["feature"] for f in result["top_factors"]] == ["MACD", "RSI14", "ATR14"]
    assert result["top_factors"][2]["shap_value"] == pytest.approx(-0.16)


def _tiny_labeled_dataset(rows: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="1D", tz="UTC")
    data = {col: rng.normal(0, 1, rows) for col in ml_models.NUMERIC_FEATURE_COLUMNS}
    for col in ml_models.CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice(["BULLISH", "BEARISH", "UNKNOWN"], size=rows)
    data["target"] = rng.choice(["BUY", "HOLD", "SELL"], size=rows)
    df = pd.DataFrame(data, index=index)
    df.index.name = "timestamp"
    return df


@pytest.mark.slow
def test_build_explainer_and_compute_shap_values_for_each_model():
    df = ml_models.prepare_dataset(_tiny_labeled_dataset(60))
    X = df[ml_models.ALL_FEATURE_COLUMNS]
    y = ml_models.encode_labels(df["target"])
    background = X.iloc[:30]
    explain_sample = X.iloc[30:35]

    for model_name, pipeline in ml_models.build_pipelines().items():
        pipeline.fit(X, y)
        shap_values, expected_value, feature_names = se.compute_shap_values(
            pipeline, model_name, explain_sample, background
        )
        n_expected_rows = 5 if model_name != ModelName.SVM else min(5, 20)  # KernelExplainer cap
        assert shap_values.shape[0] == n_expected_rows
        assert shap_values.shape[2] == 3  # 3 classes
        assert expected_value.shape == (3,)
        assert shap_values.shape[1] == len(feature_names)
