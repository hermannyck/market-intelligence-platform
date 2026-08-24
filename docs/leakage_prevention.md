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

## To be filled in by later phases

- Phase 2 (ingestion): how raw data timestamps are normalized/timezone-handled.
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
