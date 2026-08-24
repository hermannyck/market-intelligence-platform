# Architecture

## Scope

Research and decision-support platform. Operates entirely on **historical** data. Does **not**
implement real-time market data, live trading, automated order execution, broker integration,
real-money trading, or high-frequency trading.

## Module map (backend/app/)

| Module | Responsibility | Introduced |
|---|---|---|
| `config.py` | Single source of truth for assets, timeframes, indicator params, target rules, walk-forward windows, backtest assumptions | Phase 1 |
| `database/` | SQLAlchemy engine/session, ORM base (Phase 1); `User` table (Phase 13) | Phase 1 (plumbing), Phase 13 (`User`) |
| `api/` | FastAPI routers, one per nav section (`routers/`), auth/data dependencies (`deps.py`) | Phase 1 (stubs), Phase 13 (real logic) |
| `services/repository.py` | File-backed read layer the API routers call into — locates the latest relevant Phase 2-12 artifact and shapes it into JSON | Phase 13 |
| `auth/security.py` | Password hashing (bcrypt, called directly — see below) + JWT issuance/verification | Phase 13 |
| `services/` | Data ingestion (Phase 2) + cleaning (Phase 3) orchestration | Phase 2-3 |
| `features/` | Indicators (`indicators.py`, Phase 4) + derived features (`derived.py`) + multi-timeframe alignment (`multi_timeframe.py`) + orchestration (`feature_engineering.py`), Phase 5 | Phase 4-5 |
| `ml/` | Target generation (`target.py`, Phase 6) + baseline models (`models.py`, Phase 7) + ensemble | Phase 6-9 |
| `sentiment/` | News data interface (`news_data.py`) + FinBERT scoring (`finbert.py`) + timestamp-aware windowed aggregation/orchestration (`pipeline.py`) | Phase 10 |
| `regime/` | Market regime detection (`detector.py`: rule-based classifier + exploratory KMeans comparison, `pipeline.py`: orchestration) | Phase 9 |
| `explainability/` | SHAP global/local explanations (`shap_explainer.py`: explainer construction + one-hot aggregation; `pipeline.py`: orchestration) | Phase 11 |
| `backtesting/` | Historical backtest engine (`engine.py`: intrabar SL/TP simulation, notional sizing, costs, equity curve; `pipeline.py`: orchestration using `validation/`'s out-of-sample predictions) | Phase 12 |
| `validation/` | Walk-forward validation (`walk_forward.py`): configured-vs-fallback window resolution, per-window ML + simplified trading metrics, cross-window aggregation, and `generate_oos_predictions` (Phase 12's leakage-free prediction feed) | Phase 8, extended Phase 12 |

## Data flow (target end state)

```
yfinance (Phase 2)
  -> data/raw/            (immutable)
  -> data/processed/       (cleaned OHLCV, per asset x timeframe)
  -> data/features/        (indicators, multi-timeframe, regime, sentiment features)
  -> ml/ target generation -> walk-forward validation -> trained models -> models/
  -> explainability/ (SHAP on trained models)
  -> backtesting/ (predictions -> simulated trades -> equity curve)
  -> services/repository.py -> api/ (Phase 13: reads the files above, serves as JSON)
  -> frontend/ (dashboard, 8 nav pages + historical replay)
```

## Backend API (Phase 13)

All 8 real routers read from files, not a database — see `services/repository.py`'s module
docstring for why (this platform is batch-computed, not live; nothing needs duplicating into a
DB just to serve it). The only table is `users` (the login gate). Endpoints:

| Route | Serves |
|---|---|
| `POST /api/auth/register`, `/login`, `GET /me` | Real JWT auth against the `users` table |
| `GET /api/market-analysis/{asset}/{timeframe}` | OHLCV + 5 indicators + multi-timeframe bias + regime |
| `GET /api/predictions/{asset}/{timeframe}` | Latest BUY/HOLD/SELL from all 4 models + consensus |
| `GET /api/explainability/{asset}/{timeframe}/{model}` | Latest SHAP global + local report |
| `GET /api/model-lab/{asset}/{timeframe}` | Baseline comparison + walk-forward summary, all 4 models |
| `GET /api/walk-forward/{asset}/{timeframe}` | Full walk-forward report |
| `GET /api/backtesting/{asset}/{timeframe}/{model}` | Trade log, equity curve, summary |
| `GET /api/backtesting/.../performance-by-regime` | Backtest trades joined against `regime` |
| `GET /api/news-sentiment/{asset}` | Scored sample-news headlines |

**No Dashboard-specific endpoint** — "Dashboard" (nav item #1) is frontend-composed from the
others (Phase 14's job), matching Phase 1's original scaffold, which never stubbed a dedicated
dashboard route either.

## Frontend structure

React + TypeScript + Vite. `src/services/navConfig.ts` is the single source of truth for the
8 nav items (Section 13) plus the asset/timeframe/model selector options — pages and the
sidebar both read from it so they can't drift apart. A lightweight JWT login gate (kept per
the user's explicit choice, not required by the spec) sits in front of all 8 pages via
`ProtectedRoute`.

## Phase roadmap

See `../README.md` for the full 16-phase list and current status. See `model_card.md` for
honest baseline model results (Phase 7) — near-chance accuracy is the expected, documented
outcome at this stage, not a bug.

## Lessons carried over from prior related projects

Two earlier related projects (`forex-ai-dashboard`, `forex-signal-predictor`) exist elsewhere
in this workspace. This project reuses none of their code, but two bugs they hit inform
choices made here:

- `forex-ai-dashboard` hit a SQLite "database is locked" error under concurrent writes on its
  `/signals/current` endpoint. This project uses PostgreSQL from the start (Section 17 of the
  spec), which doesn't have SQLite's single-writer limitation.
- `forex-ai-dashboard`'s frontend crashed with a duplicate-React-instance "Invalid hook call"
  error inside its `AuthProvider`. This project pins exact dependency versions in
  `frontend/package.json` and keeps the dependency tree minimal to avoid two copies of React
  being bundled.
