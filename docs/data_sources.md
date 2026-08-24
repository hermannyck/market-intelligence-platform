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

Actual depth observed from the Phase 2 ingestion run (2026-08-24, see manifests in
`data/raw/*.manifest.json` for exact figures):

| Asset | M15 | H1 | D1 |
|---|---|---|---|
| EUR/USD | ~60 days (5,652 bars) | ~2 years (17,259 bars) | **2003-2026** (5,897 bars) |
| BTC/USD | ~60 days (5,632 bars) | ~2 years (17,320 bars) | **2014-2026** (4,360 bars) |
| XAU/USD (GC=F) | ~71 days (4,528 bars) | ~2 years (13,757 bars) | **2000-2026** (6,519 bars) |

D1 history turned out to go back over two decades for EUR/USD and XAU/USD, and over a decade
for BTC/USD — comfortably enough for multi-year walk-forward windows (e.g. train 2021-2023,
test 2024). Decision, made explicitly with the user rather than silently worked around:

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

## Phase 3 finding: yfinance daily OHLC inconsistency (EUR/USD, XAU/USD)

`app/services/cleaning.py::validate_and_clean` drops any bar where `close` falls outside
`[low, high]` (or `open` does). Running it on the real Phase 2 pulls surfaced a genuine data
quality issue in yfinance's **daily** bars, not a bug in the validation:

| Asset | Timeframe | Invalid-OHLC rows dropped | Rate |
|---|---|---|---|
| EUR/USD | D1 | 128 / 5,897 | 2.17% |
| XAU/USD (GC=F) | D1 | 441 / 6,519 | 6.76% |
| EUR/USD | H1 | 0 / 17,259 | 0% |
| XAU/USD (GC=F) | H1 | 0 / 13,757 | 0% |
| BTC/USD | D1, H1 | 0 | 0% |

Only **daily** EUR/USD and XAU/USD bars are affected — hourly data for the same tickers, and
all BTC/USD data, is clean. The pattern (spot-checked): `close` sits a few pips outside the
`[low, high]` range, consistent with Yahoo's daily FX/futures `Close` occasionally being
sourced from a slightly different snapshot than the day's `High`/`Low`. This is a known
characteristic of free daily forex/futures data on Yahoo Finance, not specific to this
ticker. **Decision:** drop these rows rather than "fix" them (e.g. clamping close to the
high/low range) — silently altering a price would be worse than losing the bar, and the drop
rate is small enough (≤7%) not to threaten the D1 backbone's multi-year coverage. See the
Phase 3 EDA notebook (`notebooks/phase3_data_cleaning_eda.ipynb`) for the full breakdown.

## Phase 2: ingestion implementation notes

- `backend/app/services/ingestion.py` fetches M15, H1, and D1 directly from yfinance.
  **H4 is not fetched** — yfinance has no native 4-hour interval, so H4 is derived by
  resampling H1 in Phase 3 (cleaning/processing), not invented at ingestion time.
- Every fetch is written to a new, uniquely UTC-timestamped file —
  `data/raw/{ASSET}_{TIMEFRAME}_{YYYYMMDDTHHMMSSZ}.csv` — with a sibling
  `.manifest.json` recording the ticker, requested interval/period, proxy status, actual
  row count/date range, and fetch time. Nothing in `data/raw/` is ever overwritten; a
  same-second re-run refuses rather than clobbering (`FileExistsError`).
  Raw index timestamps are kept exactly as yfinance returns them (tz-aware, in each
  ticker's native exchange timezone — UTC for EUR/USD & BTC/USD, US Eastern for XAU/USD's
  `GC=F`) rather than normalized here; normalizing to a single timezone for cross-asset
  comparison happens in Phase 3, and is recorded in `docs/leakage_prevention.md`.
- **Dependency note:** `yfinance==0.2.50` (the version originally pinned) failed with an
  empty-response error against Yahoo's current API even though direct HTTPS calls to the
  same endpoint worked fine — a crumb/cookie-handling issue fixed in the library since.
  Pinned to `yfinance==1.6.0` instead, which works. If ingestion starts failing with an
  empty-DataFrame error again, check for a newer yfinance release before assuming the data
  source itself is unavailable.
- Run it: `cd backend && .venv/Scripts/python -m app.services.ingestion` (prints a summary
  table + full per-fetch JSON). Unit tests (`backend/tests/test_ingestion.py`) mock
  yfinance entirely, so the test suite doesn't depend on network access or Yahoo's uptime.

## News data (Phase 10)

**No live or licensed historical news feed is wired up.** `data/news/sample_headlines.csv` is
a synthetic, template-generated sample instead (180 headlines, `backend/scripts/
generate_sample_news.py`, fixed seed) — real-world-plausible categories and tone variety, but
not real reported events. See `data/news/README.md` for the full rationale and generation
method.

Scored with the real `ProsusAI/finbert` pretrained model (`backend/app/sentiment/finbert.py`)
— genuine model inference, not fabricated scores. Sanity-checked against the sample's own
intended tone: positive-templated headlines average `sentiment_score` +0.61, negative average
-0.70 (see `docs/leakage_prevention.md`'s Phase 10 entry for a real case where FinBERT's tone
score and a headline's intended market implication diverged).

**Sentiment feature coverage tracks the same data-depth pattern established since Phase 2**,
because the sample's dates are weighted toward the last ~90 days/~2 years while D1 spans
decades:

| Asset | M15 | H1 | H4 | D1 |
|---|---|---|---|---|
| EUR/USD | 31.1% | 4.99% | 4.95% | 0.64% |
| BTC/USD | 34.6% | 6.56% | 6.57% | 1.26% |
| XAU/USD | 33.3% | 5.68% | 5.64% | 0.59% |

(% of rows with a non-null `sentiment_score` in the 24h short window, from the real Phase 10
pipeline run.) This is expected and documented, not a bug — most of D1's multi-decade history
predates the sample news entirely.

**Dependency notes** (see `backend/requirements.txt` for the full story): installing
`transformers`/`torch` surfaced two real environment issues, both fixed:
1. `pandas-ta` actually requires `pandas>=2.3.2`, which the original `pandas==2.2.3` /
   `numpy==2.1.3` pins violated once pip's resolver was forced to reconcile everything —
   it silently upgraded pandas all the way to 3.0.5.
2. `pyarrow==18.1.0` has a genuine Windows DLL conflict with torch (`WinError 1114` loading
   `torch/lib/c10.dll`), reproducible with nothing more than `import pyarrow; import torch` —
   unrelated to pandas or pytest. Fixed by upgrading to `pyarrow==25.0.1`.

`torch` is CPU-only and not on the default PyPI index — install it separately:
`pip install torch --index-url https://download.pytorch.org/whl/cpu`.
