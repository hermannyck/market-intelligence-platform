# data/news/

Historical financial news + FinBERT sentiment scores, timestamp-aware and asset-tagged
(Phase 10).

**`sample_headlines.csv` is a synthetic, template-generated sample dataset — not a real
historical news archive.** A genuine multi-year historical financial news archive requires a
licensed data vendor (e.g. RavenPack, Dow Jones, Bloomberg) this project doesn't have. Per the
spec's own explicit contingency (Section 7): *"If historical news data is unavailable during
the initial implementation, create a clean news-data interface and use a clearly documented
sample/historical dataset rather than pretending that future news is available."* This is that
dataset. It's produced by `backend/scripts/generate_sample_news.py` (fixed random seed,
reproducible) — real-world-plausible categories of financial news (central bank decisions,
macro data, regulatory news, risk sentiment) with realistic positive/negative/neutral tone
variety, but no headline claims a specific real event happened. 180 headlines (60 per asset),
dates weighted toward the last ~90 days / ~2 years to roughly track where this project's H1/M15
OHLCV history actually exists (see `docs/data_sources.md`) — it does **not** attempt to cover
D1's multi-decade backbone, and that gap is documented, not hidden (see
`docs/leakage_prevention.md`'s Phase 10 entry).

`scored_headlines.parquet` — the same headlines run through FinBERT once
(`backend/app/sentiment/finbert.py`, `ProsusAI/finbert`), cached so re-running the pipeline
doesn't re-score unchanged text. Real model output, not fabricated: FinBERT's scores track the
headlines' intended tone well in aggregate (positive-templated headlines average
`sentiment_score` +0.61, negative average -0.70) but not perfectly — see the Phase 10
leakage-prevention entry for a genuine case where it didn't.

To regenerate the sample dataset:

```bash
cd backend
.venv\Scripts\python scripts/generate_sample_news.py
```
