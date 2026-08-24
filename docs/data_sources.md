# Data sources

## Current source: yfinance (Phase 2+)

No API key required. Asset → ticker mapping (see `backend/app/config.py::ASSETS`):

| Asset | Ticker | Notes |
|---|---|---|
| EUR/USD | `EURUSD=X` | |
| BTC/USD | `BTC-USD` | |
| XAU/USD | `GC=F` | **Proxy.** COMEX gold futures, not literal spot XAU/USD. Standard free substitute; documented here rather than silently treated as identical. |

## Known limitation: intraday history depth

yfinance realistically provides:

- **15-minute (M15):** ~60 days of history
- **60-minute (H1, and H4 by resampling):** ~730 days of history
- **Daily (D1):** effectively unlimited (years)

This is well short of the multi-year windows the walk-forward validation spec describes
(e.g. train 2021-2023, test 2024). Decision, made explicitly with the user rather than
silently worked around:

- **D1 is the multi-year backbone.** Full walk-forward validation and backtesting across
  multi-year windows (2021-2025 style) are demonstrated primarily on D1.
- **M15/H1/H4 are populated with whatever depth is actually available** and are labeled as
  limited-depth windows everywhere they're surfaced (dashboard, reports, docs) — never
  presented as if they had the same multi-year history as D1.
- Multi-timeframe *bias* (M15 → H1 → H4 → D1 direction + overall bias, spec Section 2) is
  still fully implementable over the recent window where all four timeframes overlap; it's
  the multi-year *walk-forward validation* specifically that's D1-led.

If deeper intraday history becomes a requirement later, the ingestion layer in
`backend/app/services/` is the single place a new provider would plug in — nothing else in
the pipeline should need to change, since everything downstream consumes `data/processed/`
in a source-agnostic OHLCV schema.

## News data (Phase 10)

Historical financial news + FinBERT sentiment. If no live historical news feed is wired up
in the initial implementation, `data/news/` holds a clearly documented sample/historical
dataset instead of pretending future news is available. See `data/news/README.md`.
