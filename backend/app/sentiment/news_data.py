"""Phase 10: news data interface.

A clean, small interface over `data/news/sample_headlines.csv` — the documented sample dataset
(see `scripts/generate_sample_news.py` and `data/news/README.md`), kept separate from the
FinBERT scoring step so a future phase can point this at a real historical news vendor without
touching anything else in the sentiment pipeline (spec Section 7's "clean news-data interface"
requirement).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NEWS_DIR = PROJECT_ROOT / "data" / "news"
SAMPLE_HEADLINES_PATH = NEWS_DIR / "sample_headlines.csv"


def load_news(asset_key: str | None = None, path: Path | None = None) -> pd.DataFrame:
    """Loads the news dataset, optionally filtered to one asset. `published_at` is parsed to a
    tz-aware UTC datetime column (not the index -- callers typically need both `published_at`
    and `headline`)."""
    path = path or SAMPLE_HEADLINES_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"No news data at {path}. Run `python scripts/generate_sample_news.py` first."
        )
    df = pd.read_csv(path)
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    if asset_key is not None:
        df = df[df["asset_key"] == asset_key].reset_index(drop=True)
    return df.sort_values("published_at").reset_index(drop=True)
