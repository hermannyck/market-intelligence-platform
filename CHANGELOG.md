# Changelog

This project was built incrementally over 16 phases, each proposed, implemented, and verified
before the next began (per the original spec's Section 22). This file is a skimmable summary of
what each phase actually delivered and the real findings it produced — the authoritative detail
lives in each phase's own commit message, in `docs/leakage_prevention.md` (leakage reasoning per
phase), `docs/model_card.md` (model results), and `docs/data_sources.md` (data-depth findings).

## Phase 1 — Project architecture

FastAPI + React/TS/Vite skeleton: folder structure, `app/config.py` as the single source of
truth for assets/timeframes/indicators/target/walk-forward/backtest settings, a `/health`
endpoint, 8 stub nav pages behind a JWT login gate (kept by explicit user choice, not required
by the spec). No indicators, models, or business logic yet.

## Phase 2 — Historical data ingestion

`yfinance` pulls for EUR/USD (`EURUSD=X`), BTC/USD (`BTC-USD`), XAU/USD (`GC=F`, a documented
gold-futures proxy) across M15/H1/D1 into `data/raw/` (H4 deliberately not fetched — derived
later from H1). D1 history goes back to 2000–2014 depending on asset, far deeper than the
~730-day worry from planning.

## Phase 3 — Data cleaning and EDA

Raw → UTC-normalized, schema-validated `data/processed/`. Drops duplicates/NaN/invalid-OHLC
rows (counted, never patched), reports gaps (never fills them), derives H4 from H1 via
left-closed 4-hour buckets. Real finding: yfinance's daily EUR/USD and XAU/USD bars have a
genuine ~2–7% invalid-OHLC rate.

## Phase 4 — Five technical indicators

EMA(20/50/200), RSI(14), MACD(12/26/9), ATR(14), Bollinger Bands(20, 2σ) via `pandas-ta`.
No-lookahead proven directly by recomputing on a truncated series and checking bit-identical
output up to the truncation point — the pattern every later "no lookahead" claim in this project
reuses.

## Phase 5 — Feature engineering

Derived ratios/returns plus multi-timeframe bias, joined via `as_of_join`'s close-time-based
`merge_asof` (a bar is only "available" once it has actually closed — the central
multi-timeframe leakage hazard). Real finding: M15/H1 bias coverage is honestly sparse for
older D1 history, a direct consequence of Phase 2's data-depth limits.

## Phase 6 — Target generation

BUY/HOLD/SELL from a volatility-adjusted threshold (`0.5 × ATR14/close`), horizon 12 bars,
configurable. Real finding: HOLD is the *minority* class everywhere (15–23%), not dominant.

## Phase 7 — Baseline ML models

Logistic Regression, Random Forest, SVM, XGBoost as scikit-learn Pipelines, chronological
80/20 split, `StandardScaler` fit-on-train-only by construction. Honest finding
(`docs/model_card.md`): the best model beat a naive majority-class baseline in only 3/12
combinations — near-chance accuracy, motivating Phase 8.

## Phase 8 — Walk-forward validation

Multiple expanding train/test windows, fresh Pipelines per window, classification + a
simplified trading diagnostic kept explicitly separate. Standout finding: XAU/USD D1 SVM
averaged 51% accuracy across 4 windows — worth the SHAP investigation in Phase 11.

## Phase 9 — Market regime detection

Rule-based classifier (5 regimes) chosen over live clustering specifically to avoid leaking the
whole series' distribution into early labels; KMeans implemented too, but explicitly
retrospective/EDA-only, never a live feature. Sideways/Range-Bound dominates (43–57%).

## Phase 10 — News sentiment (FinBERT)

Real FinBERT inference on a documented *synthetic* sample news dataset (no licensed real news
archive available). Timestamp-aware windowed aggregation relative to each bar's own close time
— a real bug (stale windows) caught and fixed before shipping.

## Phase 11 — SHAP explainability

Global + local explanations for all 4 models (TreeExplainer/LinearExplainer/KernelExplainer).
Confirmed the XAU/USD D1 SVM standout's local explanation is appropriately unconfident,
consistent with its real ~51% accuracy.

## Phase 12 — Backtesting

The realistic engine: notional position sizing, transaction costs, spread, intrabar ATR-based
stop-loss/take-profit, driven only by genuinely out-of-sample walk-forward predictions — never
the true label (verified structurally, not just by convention). Striking finding: XAU/USD D1
SVM's simplified Phase 8 diagnostic (+815% mean return) became a real +2.9% / -2.8% max drawdown
once costs and risk management were modeled — the clearest before/after in the whole project.

## Phase 13 — Backend API

Real endpoints for all 8 nav sections, reading straight from Phases 2–12's output files (no
database needed except for the `users` table). Real JWT auth, `bcrypt` called directly (not
`passlib`, which breaks against modern `bcrypt`).

## Phase 14 — React dashboard (real data)

All 8 pages wired to the real API: typed client, design-token CSS system, 6 Recharts
components (including a custom candlestick chart — Recharts has no native one). Verified with a
full manual click-through and zero console errors.

## Phase 15 — Historical Replay Mode

A 9th page: step or auto-play bar-by-bar through the walk-forward out-of-sample signal history,
restricted *by construction* to bars with a genuine OOS signal — never a hindsight-informed
frame. Two real bugs caught during live verification (a timestamp-format mismatch and a
too-small fetch limit that truncated H1 history) — both are exactly the class of silent
data-corruption bug this project's leakage discipline exists to catch.

## Phase 16 — Testing and documentation (this phase)

- Backend: 160 tests, 91% statement coverage (measured with `pytest-cov`, not estimated).
  Closed real gaps: an auth edge case (valid token, deleted user), the app's documented
  database-unreachable resilience claim, and three defensive branches in the backtest engine.
- Frontend: first automated test suite (Vitest), targeted at `replayFrames.ts` — the exact
  join logic that produced Phase 15's two real bugs.
- Dependency hygiene: closed a critical `vitest` RCE advisory and a high-severity
  `react-router-dom` open-redirect advisory (both patchable within their existing major
  version); two remaining advisories documented as accepted risk in `docs/testing.md`.
- New `docs/testing.md` (test strategy, real coverage numbers, what's intentionally excluded
  and why) and this changelog.

See `README.md` for current setup/run instructions and `docs/architecture.md` for the module
map. This platform is **not a live trading system** — see the disclaimer at the top of
`README.md`.
