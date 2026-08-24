# AI-Powered Multi-Asset Market Intelligence and Explainable Trading Signal Prediction Platform

> **This is not a live trading system.** It operates entirely on historical data to support
> historical analysis, model training, validation, prediction, explainability, and
> backtesting. It does not stream real-time market data, place orders, connect to a broker,
> execute trades, or provide guaranteed financial predictions. Predictions are not financial
> advice.

A research platform combining historical multi-asset, multi-timeframe technical analysis,
market regime detection, financial news sentiment, machine learning, model ensembling,
explainable AI, walk-forward validation, and backtesting into a transparent research
dashboard.

## Scope

- **Assets:** EUR/USD, BTC/USD, XAU/USD (architecture supports adding more without major
  changes — see `backend/app/config.py::ASSETS`)
- **Timeframes:** M15, H1, H4, D1
- **Indicators:** EMA (20/50/200), RSI (14), MACD (12/26/9), ATR (14), Bollinger Bands (20, 2σ)
  — exactly these five
- **Models:** Logistic Regression, Random Forest, SVM, XGBoost, plus an optional ensemble
- **Validation:** time-aware walk-forward validation (no random shuffling of time-series data)

See the full requirements this project was scoped from for the complete spec; this README
tracks what's actually built.

## Status

**All 16 phases are complete.** See `docs/architecture.md` for the module map and
`CHANGELOG.md` for a phase-by-phase summary of what was actually delivered and found.

| Phase | Status |
|---|---|
| 1. Project architecture | ✅ done |
| 2. Historical data ingestion | ✅ done |
| 3. Data cleaning and EDA | ✅ done |
| 4. Five technical indicators | ✅ done |
| 5. Feature engineering | ✅ done |
| 6. Target generation | ✅ done |
| 7. Baseline ML models | ✅ done |
| 8. Walk-forward validation | ✅ done |
| 9. Market regime detection | ✅ done |
| 10. News sentiment (FinBERT) | ✅ done |
| 11. SHAP explainability | ✅ done |
| 12. Backtesting | ✅ done |
| 13. Backend API (real endpoints) | ✅ done |
| 14. React dashboard (real data) | ✅ done |
| 15. Historical replay mode | ✅ done |
| 16. Testing and documentation | ✅ done |

## Project layout

```
backend/    FastAPI app (app/api, models, services, ml, features, sentiment, regime,
            backtesting, validation, explainability, database) + backend/tests/
frontend/   React + TypeScript + Vite dashboard + frontend/src/utils/*.test.ts (Vitest)
data/       raw/ processed/ features/ news/  (raw/ is never overwritten)
models/     trained model artifacts (Phase 7+)
notebooks/  exploratory analysis
tests/      cross-cutting/integration tests
docs/       architecture, data sources, leakage-prevention decisions, model card, testing
CHANGELOG.md  phase-by-phase summary of what was built and found
```

## Running it

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cpu  # first, separately (Phase 10)
.venv\Scripts\pip install -r requirements.txt   # Windows
set DATABASE_URL=sqlite:///./dev.db             # local dev fallback -- see Database section below
pytest                                           # 160 tests (a few are @pytest.mark.slow -- real FinBERT/SHAP inference)
pytest --cov=app --cov-report=term-missing       # 91% statement coverage -- see docs/testing.md
uvicorn app.main:app --reload                    # serves http://127.0.0.1:8000 -- see /docs for the full API
```

**Frontend** (Phase 14 — real API integration: typed client, JWT auth against `/api/auth`,
asset/timeframe/model selectors driving every page, 6 Recharts components). On Windows, if
`npm run dev` can't find `node` because PATH isn't inherited by your shell, use
`frontend/dev-server.cmd` instead, which sets `PATH` explicitly before calling `npm run dev`.

```bash
cd frontend
npm install
npm run build   # type-checks + production build
npm run test     # Vitest (Phase 16) -- unit tests for src/utils/replayFrames.ts
npm run dev      # serves http://127.0.0.1:5173 — login/register -> 9 real data-driven pages
```

**Data ingestion** (Phase 2 — pulls EUR/USD, BTC/USD, XAU/USD across M15/H1/D1 into
`data/raw/`; H4 is derived later by resampling H1, see `docs/data_sources.md`)

```bash
cd backend
.venv\Scripts\python -m app.services.ingestion
```

**Data cleaning** (Phase 3 — raw -> `data/processed/`: UTC normalization, dedup/NaN/invalid-
OHLC removal, gap reporting, H4 derived from H1). See
`notebooks/phase3_data_cleaning_eda.ipynb` for the EDA writeup.

```bash
cd backend
.venv\Scripts\python -m app.services.cleaning
```

**Feature engineering** (Phase 5 — `data/processed/` -> `data/features/`: the 5 indicators +
derived ratios/returns + multi-timeframe bias, per asset/timeframe). See
`docs/leakage_prevention.md` for how look-ahead is avoided in the multi-timeframe join.

```bash
cd backend
.venv\Scripts\python -m app.features.feature_engineering
```

**Target generation** (Phase 6 — configurable forward-horizon, volatility-adjusted
BUY/HOLD/SELL label appended on top of `data/features/`). See `docs/leakage_prevention.md`
for the exact leakage boundary between features and the label.

```bash
cd backend
.venv\Scripts\python -m app.ml.target
```

**Baseline ML models** (Phase 7 — Logistic Regression / Random Forest / SVM / XGBoost, one
chronological train/test split per asset/timeframe, saved to `models/`). **Read
`docs/model_card.md` before trusting any number this prints** — baseline accuracy is honestly
near chance, documented on purpose, not a bug.

```bash
cd backend
.venv\Scripts\python -m app.ml.models
```

**Walk-forward validation** (Phase 8 — multiple expanding train/test windows per
asset/timeframe; falls back to a data-driven window scheme where the spec's 2021-2025 example
dates don't fit the actual history available, e.g. M15). Per-window ML metrics (incl.
ROC-AUC) plus a simplified trading diagnostic, saved to `models/`.

```bash
cd backend
.venv\Scripts\python -m app.validation.walk_forward
```

**Market regime detection** (Phase 9 — rule-based Bullish/Bearish Trending, Sideways/
Range-Bound, High/Low Volatility, appended to `data/features/`). See
`notebooks/phase9_regime_detection_eda.ipynb` for the distribution/clustering-comparison
writeup.

```bash
cd backend
.venv\Scripts\python -m app.regime.pipeline
```

**News sentiment** (Phase 10 — FinBERT on a documented synthetic sample news dataset, joined
timestamp-aware onto `data/features/`). **Read `data/news/README.md` first** — the news
dataset is not real historical news. `torch` must be installed separately first (see
`backend/requirements.txt`).

```bash
cd backend
.venv\Scripts\python -m app.sentiment.pipeline
```

**SHAP explainability** (Phase 11 — global feature importance + local per-prediction
explanations for all 4 models, saved to `models/`). SVM explanations are capped to a small
sample size (see `docs/leakage_prevention.md`'s Phase 11 entry) since `KernelExplainer` is
~1000x slower than the TreeExplainer/LinearExplainer used for the other 3 models.

```bash
cd backend
.venv\Scripts\python -m app.explainability.pipeline
```

**Backtesting** (Phase 12 — the real engine: configurable capital, notional position sizing,
transaction costs, spread, intrabar ATR-based stop-loss/take-profit, driven by genuinely
out-of-sample walk-forward predictions, never the true label). Distinct from Phase 8's
simplified trading diagnostic — see `docs/leakage_prevention.md`'s Phase 12 entry. As of Phase
15, the saved report also persists the full per-bar OOS `signals` series (not just the trades
that resulted from it) — Historical Replay Mode's data source. Reports saved before Phase 15
won't have this field (the "never overwrite" convention leaves them as-is); re-run this command
to get a fresh report with `signals` included.

```bash
cd backend
.venv\Scripts\python -m app.backtesting.pipeline
```

**Backend API** (Phase 13 — real endpoints for all 8 nav sections, reading straight from the
files the phases above produced, plus a real JWT login gate). See `docs/architecture.md`'s
Backend API section for the full endpoint list, and `docs/leakage_prevention.md`'s Phase 13
entry for why `/api/predictions` necessarily serves Phase 7's baseline model rather than a
walk-forward-validated one.

```bash
cd backend
.venv\Scripts\uvicorn app.main:app --reload
# then open http://127.0.0.1:8000/docs for interactive API docs
```

**Database** — the spec's stated choice is PostgreSQL (`app.config.SETTINGS.database_url`
defaults to it), needed only for the `users` table (the login gate). Only used starting Phase
13 (auth) — every other endpoint works with no database at all.

```bash
docker compose up -d postgres
```

If Docker/PostgreSQL aren't available (this project was developed without either installed),
use SQLite for local dev instead — set `DATABASE_URL=sqlite:///./dev.db` before running the
server or tests. `app/database/models.py::User` uses plain, DB-agnostic column types so it
works identically either way.

**React dashboard** (Phase 14 — all 8 nav pages wired to the real Phase 13 API: candlestick +
indicator charts, predictions with consensus, SHAP explainability, model lab, walk-forward
report, backtest equity curve + trade log, news sentiment timeline). Verified with a full
manual click-through against real generated data (zero console errors); see `docs/testing.md`
for what is and isn't covered by the Vitest suite Phase 16 added. **Phase 15 adds a 9th page,
Historical Replay** — step or auto-play bar-by-bar through the walk-forward out-of-sample
signal history for the selected asset/timeframe/model, watching the price chart, model signal,
regime, and equity curve unfold together. Restricted by construction to bars with a genuine OOS
signal — see `docs/leakage_prevention.md`'s Phase 15 entry for why. Requires a Phase 15-or-later
backtest report (re-run the command above if yours predates it).

```bash
cd backend
.venv\Scripts\uvicorn app.main:app --reload
# in a second terminal:
cd frontend
npm run dev
# open http://127.0.0.1:5173, register an account, and log in
```

## Deploying this publicly

Everything above runs locally. To put it on the public internet (a real URL anyone can open),
see **`docs/deploying.md`** — a step-by-step runbook (backend + Postgres on Render via the
included `render.yaml`, frontend as a static build on Vercel), plus the environment variables
you need to set (`backend/.env.example`) and a startup safety check that refuses to run in
production with the default JWT secret.

## Design principles (from the project spec)

1. Correctness
2. Reproducibility
3. Prevention of data leakage — see `docs/leakage_prevention.md`
4. Explainability
5. Robust evaluation
6. Clean software architecture
7. User-friendly visualization
8. Academic quality
