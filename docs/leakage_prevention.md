# Leakage prevention — living document

Per spec Section 19, this document records every leakage-prevention decision as it's made.
It is a living document — later phases append to it rather than this being written once
upfront.

## Phase 1 (this phase)

No data, features, or models exist yet, so there is nothing to leak. What Phase 1 establishes
structurally, in anticipation of later phases:

- `config.py::TARGET` centralizes the forward horizon and threshold so target generation
  (Phase 6) has one place to define "future" precisely, rather than each caller computing it
  differently.
- `config.py::DEFAULT_WALK_FORWARD_WINDOWS` uses explicit, non-overlapping train/test date
  ranges (expanding window) rather than a random split, so Phase 8 has a concrete, inspectable
  starting point instead of inventing one under time pressure.
- `data/raw/README.md` establishes the "never overwrite raw data" rule from day one, before
  any ingestion code exists that could violate it.

## Phase 2 (historical data ingestion)

- Raw timestamps are **not** normalized at ingestion time — each asset's raw CSV keeps
  yfinance's native index timezone (UTC for EUR/USD & BTC/USD; US Eastern for XAU/USD's
  `GC=F` proxy). This is a deliberate choice: raw data stays exactly as pulled from the
  source (nothing here should be "corrected" before it's even been looked at), and timezone
  normalization to a single UTC axis for cross-asset/cross-timeframe alignment is deferred
  to Phase 3, where it can be tested and verified rather than silently baked into ingestion.
  **Anyone consuming `data/raw/` directly must not assume a common timezone across assets.**
- H4 is not ingested at all in Phase 2 — it will be derived in Phase 3 by resampling H1 bars
  using only bars whose *close* time has already occurred (i.e. a resampled H4 bar is only
  considered "available" once all four of its constituent H1 bars have closed). This rule is
  recorded here now so Phase 3's resampling implementation has a concrete spec to satisfy,
  not just "resample to 4h" left ambiguous.
- Every raw fetch's manifest records `fetched_at_utc` and the exact `first_timestamp`/
  `last_timestamp` returned, so any later analysis can prove which raw snapshot it used and
  confirm no fetch silently included data past its stated range.

## To be filled in by later phases
- Phase 4-5 (indicators/features): confirmation that every indicator/feature at row *t* uses
  only bars ≤ *t*.
- Phase 2's multi-timeframe alignment: how a lower-timeframe row looks up its parent
  higher-timeframe value without peeking at a not-yet-closed higher-timeframe bar.
- Phase 6 (target generation): the exact leakage boundary between feature columns and the
  future-return-derived label.
- Phase 7 (models): confirmation that `StandardScaler`/other preprocessing is fit only on
  each walk-forward window's training fold, never on test data or the full dataset.
- Phase 9 (regime detection): confirmation regime labels at time *t* use no data after *t*.
- Phase 10 (sentiment): confirmation no article published after the prediction timestamp is
  used.
