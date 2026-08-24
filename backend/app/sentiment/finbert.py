"""Phase 10: FinBERT sentiment scoring (spec Section 7 — "use a pretrained financial
sentiment model such as FinBERT where practical," not training an LLM from scratch).

Uses `ProsusAI/finbert` (`app.config.SENTIMENT.finbert_model_name`), a BERT model fine-tuned
specifically for financial-text 3-class sentiment (positive/negative/neutral), downloaded once
from Hugging Face and cached locally by the `transformers` library — not trained here.

This module only *scores text*; it has no notion of timestamps, assets, or which article is
"allowed" for which prediction — that timestamp-aware join lives in `app.sentiment.pipeline`,
kept deliberately separate so the scoring step (a pure function of text -> probabilities) can't
accidentally develop a dependency on time ordering.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.config import SENTIMENT

POSITIVE = "positive"
NEGATIVE = "negative"
NEUTRAL = "neutral"


@lru_cache(maxsize=1)
def _load_model():
    """Loaded lazily and cached (module-level singleton) -- importing this module must not by
    itself trigger a multi-hundred-MB model download; only calling score_texts() does."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(SENTIMENT.finbert_model_name)
    model = AutoModelForSequenceClassification.from_pretrained(SENTIMENT.finbert_model_name)
    model.eval()
    return tokenizer, model


def score_texts(texts: list[str], batch_size: int = 16) -> pd.DataFrame:
    """Returns one row per input text: positive_prob/negative_prob/neutral_prob (softmax
    output, sum to 1) and sentiment_score = positive_prob - negative_prob (a standard
    continuous FinBERT convention: +1 = maximally positive, -1 = maximally negative, ~0 =
    neutral or conflicting signal)."""
    import torch

    if not texts:
        return pd.DataFrame(columns=["positive_prob", "negative_prob", "neutral_prob", "sentiment_score"])

    tokenizer, model = _load_model()
    id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}

    rows = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            inputs = tokenizer(batch, padding=True, truncation=True, max_length=64, return_tensors="pt")
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1).numpy()
            for row_probs in probs:
                by_label = {id2label[i]: float(p) for i, p in enumerate(row_probs)}
                rows.append(
                    {
                        "positive_prob": by_label.get(POSITIVE, 0.0),
                        "negative_prob": by_label.get(NEGATIVE, 0.0),
                        "neutral_prob": by_label.get(NEUTRAL, 0.0),
                        "sentiment_score": by_label.get(POSITIVE, 0.0) - by_label.get(NEGATIVE, 0.0),
                    }
                )
    return pd.DataFrame(rows)
