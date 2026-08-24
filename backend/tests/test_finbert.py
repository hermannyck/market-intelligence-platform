"""Phase 10 tests for app.sentiment.finbert. These actually load the real FinBERT model (a
one-time download cached by `transformers`) and run real inference -- slower than the rest of
the suite, but this is the one place that needs to prove the pretrained model itself is wired
up correctly, not just mocked.
"""
from __future__ import annotations

import pytest

from app.sentiment import finbert


def test_score_texts_empty_list_returns_empty_dataframe():
    result = finbert.score_texts([])
    assert len(result) == 0
    assert list(result.columns) == ["positive_prob", "negative_prob", "neutral_prob", "sentiment_score"]


@pytest.mark.slow
def test_score_texts_probabilities_are_valid_distribution():
    result = finbert.score_texts(["Profits soared as the company beat expectations."])
    row = result.iloc[0]
    assert row["positive_prob"] + row["negative_prob"] + row["neutral_prob"] == pytest.approx(1.0, abs=1e-4)
    for col in ("positive_prob", "negative_prob", "neutral_prob"):
        assert 0.0 <= row[col] <= 1.0
    assert -1.0 <= row["sentiment_score"] <= 1.0


@pytest.mark.slow
def test_score_texts_distinguishes_positive_from_negative():
    result = finbert.score_texts(
        [
            "Profits soared as the company smashed earnings expectations.",
            "The company collapsed into bankruptcy after a catastrophic loss.",
        ]
    )
    positive_row, negative_row = result.iloc[0], result.iloc[1]
    assert positive_row["sentiment_score"] > negative_row["sentiment_score"]
    assert positive_row["positive_prob"] > positive_row["negative_prob"]
    assert negative_row["negative_prob"] > negative_row["positive_prob"]


@pytest.mark.slow
def test_score_texts_batches_do_not_change_results():
    texts = ["Stocks rallied on strong earnings."] * 3 + ["Markets fell on recession fears."] * 3
    batched = finbert.score_texts(texts, batch_size=2)
    unbatched = finbert.score_texts(texts, batch_size=100)
    import pandas as pd

    pd.testing.assert_frame_equal(
        batched.reset_index(drop=True), unbatched.reset_index(drop=True), atol=1e-5
    )
