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

Currently on **Phase 1 — Project architecture**. See `docs/architecture.md` for the module
map and the full 16-phase roadmap. Each phase is built and verified before the next begins.

| Phase | Status |
|---|---|
| 1. Project architecture | ✅ done |
| 2. Historical data ingestion | ✅ done |
| 3. Data cleaning and EDA | not started |
| 4. Five technical indicators | not started |
| 5. Feature engineering | not started |
| 6. Target generation | not started |
| 7. Baseline ML models | not started |
| 8. Walk-forward validation | not started |
| 9. Market regime detection | not started |
| 10. News sentiment (FinBERT) | not started |
| 11. SHAP explainability | not started |
| 12. Backtesting | not started |
| 13. Backend API (real endpoints) | not started |
| 14. React dashboard (real data) | not started |
| 15. Historical replay mode | not started |
| 16. Testing and documentation | not started |

## Project layout

```
backend/    FastAPI app (app/api, models, services, ml, features, sentiment, regime,
            backtesting, validation, explainability, database)
frontend/   React + TypeScript + Vite dashboard
data/       raw/ processed/ features/ news/  (raw/ is never overwritten)
models/     trained model artifacts (Phase 7+)
notebooks/  exploratory analysis
tests/      cross-cutting/integration tests
docs/       architecture, data sources, leakage-prevention decisions
```

## Running it (Phase 1: skeleton only)

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
pytest                                           # 2 passing smoke tests
uvicorn app.main:app --reload                    # serves http://127.0.0.1:8000/health
```

**Frontend**

```bash
cd frontend
npm install
npm run build   # type-checks + production build
npm run dev      # serves http://127.0.0.1:5173 — login screen -> 8 nav page stubs
```

**Data ingestion** (Phase 2 — pulls EUR/USD, BTC/USD, XAU/USD across M15/H1/D1 into
`data/raw/`; H4 is derived later by resampling H1, see `docs/data_sources.md`)

```bash
cd backend
.venv\Scripts\python -m app.services.ingestion
```

**Database** (not required until Phase 6+)

```bash
docker compose up -d postgres
```

## Design principles (from the project spec)

1. Correctness
2. Reproducibility
3. Prevention of data leakage — see `docs/leakage_prevention.md`
4. Explainability
5. Robust evaluation
6. Clean software architecture
7. User-friendly visualization
8. Academic quality
