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
| `GET /api/backtesting/{asset}/{timeframe}/{model}` | Trade log, equity curve, summary, **+ full per-bar OOS `signals` (Phase 15)** |
| `GET /api/backtesting/.../performance-by-regime` | Backtest trades joined against `regime` |
| `GET /api/news-sentiment/{asset}` | Scored sample-news headlines |

**No Dashboard-specific endpoint** — "Dashboard" (nav item #1) is frontend-composed from the
others (Phase 14's job), matching Phase 1's original scaffold, which never stubbed a dedicated
dashboard route either. **No Historical Replay-specific endpoint either** (Phase 15) — the
replay page composes the existing `market-analysis` and `backtesting` responses client-side;
see the Frontend structure section below.

## Frontend structure (Phase 1 scaffold, Phase 14 real data, Phase 15 replay mode, Phase 16 tests)

React + TypeScript + Vite. `src/services/navConfig.ts` is the single source of truth for the
8 nav items (Section 13) plus the asset/timeframe/model selector options — pages and the
sidebar both read from it so they can't drift apart. A lightweight JWT login gate (kept per
the user's explicit choice, not required by the spec) sits in front of all 8 pages via
`ProtectedRoute`, now against the real Phase 13 `/api/auth` endpoints (Phase 1's version
accepted any input).

- `src/api/client.ts` + `types.ts` — a small typed fetch wrapper (token attached from
  `localStorage` automatically) and TypeScript types mirroring the backend's JSON shapes.
  Deliberately loose/`unknown`-tolerant in places, matching Phase 13's own choice not to wrap
  every response in a rigid schema.
- `src/hooks/useApiData.ts` — the one data-fetching hook every page uses: tracks
  loading/error/not-found uniformly, and treats a 404 as "this pipeline phase hasn't been run
  for this combination yet" (rendered as a friendly empty state) rather than a hard error.
- `src/hooks/useSelection.tsx` — the asset/timeframe/model selection state lives here (not in
  each page), so the sidebar's selectors drive every page's data fetch consistently.
- `src/charts/` — Recharts-based components: `CandlestickChart` (built from two layered range
  Bars — a thin wick + wider body — since Recharts has no native candlestick), indicator mini
  charts (RSI/MACD/ATR), `EquityCurveChart`, `ShapBarChart` (global importance and signed local
  explanations), `SentimentTimelineChart`, `RegimeDistributionChart`.
- Design tokens (`index.css`) follow the project's `dataviz` skill palette — light/dark aware
  CSS custom properties (`--series-1..8`, `--status-good/warning/serious/critical`, etc.),
  BUY/HOLD/SELL always rendered as colored badges, never color-only.
- Phase 14 itself shipped with no frontend automated test suite — a deliberate scope decision
  (matching the sibling `forex-signal-predictor` project's own explicit choice for the same
  reason); verification for this phase was a full manual click-through of all 8 pages against
  the real backend and real generated data, checked for console errors at every step. Phase 16
  later added a first, narrowly-scoped Vitest suite once Phase 15 demonstrated a concrete need
  for one — see `docs/testing.md`.
- **`src/pages/ReplayPage.tsx` (Phase 15) — Historical Replay Mode**, a 9th page beyond the
  spec's 8-page nav. Fetches `market-analysis` (a large `limit`) and `backtesting` (which now
  also returns the full per-bar `signals` series — see Backend API above) for the current
  asset/timeframe/model, and joins them client-side into a `ReplayFrame[]` timeline — filtered
  to only bars with a real out-of-sample signal, so scrubbing through it can never show a
  hindsight-informed frame (see `docs/leakage_prevention.md`'s Phase 15 entry for why this
  filter is the whole point of the feature). Playback state (current index, playing/paused,
  speed) is plain `useState`/`useEffect` with a `setInterval` driving the index forward — no new
  library. Reuses `CandlestickChart` (a rolling window ending at the current frame) and
  `EquityCurveChart` (progressively revealed) rather than introducing new chart components.
- **`src/utils/replayFrames.ts` (Phase 16)** — `ReplayPage`'s bar/signal/trade/equity join logic,
  extracted out of the page component specifically so it can be unit-tested without rendering
  anything or mocking `fetch`. `replayFrames.test.ts` (Vitest) pins down the exact timestamp-
  format-mismatch bug Phase 15 hit live, plus filtering/sorting/event-attachment behavior — see
  `docs/testing.md` for the full rationale and what this suite deliberately does not attempt to
  cover (no component/DOM tests).

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
