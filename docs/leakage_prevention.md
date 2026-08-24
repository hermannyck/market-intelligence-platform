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

## Phase 3 (data cleaning)

- **Timestamps are normalized to UTC** in `standardize()` — raw files keep each ticker's
  native exchange timezone (see Phase 2 entry above), but everything from `data/processed/`
  onward is on a single UTC axis, required for correctly aligning M15/H1/H4/D1 bars against
  each other in later multi-timeframe feature work (Phase 5) without an off-by-one timezone
  bug silently pulling in a bar that hadn't closed yet.
- **H4 closed-bar rule implemented exactly as specified in the Phase 2 entry above**:
  `resample_h4_from_h1()` groups H1 bars into left-closed, left-labeled 4-hour buckets and
  keeps a bucket only when its `count() == 4` — i.e. all four constituent H1 bars are present.
  A trailing partial bucket (fewer than 4 H1 bars, e.g. because the raw pull's coverage ends
  mid-block) is dropped rather than emitted as an incomplete/leaky bar. Verified with a unit
  test (`test_resample_h4_drops_incomplete_trailing_bucket`) using a 10-bar H1 series that
  should yield exactly 2 complete H4 buckets.
- **Gaps are reported, never filled.** `analyze_gaps()` only measures and records gap sizes —
  no interpolation, no forward-fill, no synthetic bars. Filling a weekend gap with an
  interpolated price would let a model "see" a smooth path through a period the market was
  actually closed, which is itself a subtle form of leakage (information that never existed).
- **Cleaning drops are counted, not silently absorbed.** Every processed manifest records
  `duplicates_dropped` / `nan_dropped` / `non_positive_price_dropped` / `invalid_ohlc_dropped`,
  so any later result can be traced back to exactly what was removed and why (see the Phase 3
  EDA notebook, `notebooks/phase3_data_cleaning_eda.ipynb`, for the real numbers — yfinance's
  daily EUR/USD and XAU/USD bars have a genuine ~2-7% invalid-OHLC rate, documented in
  `docs/data_sources.md` rather than silently patched).
- **Full provenance chain**: every processed manifest's `source_raw_manifest` field points
  back to the exact raw manifest it was built from, which itself records the exact yfinance
  pull it came from — so any processed dataset's lineage back to the original API response is
  traceable.

## Phase 4 (technical indicators)

- **Verified, not assumed, no-lookahead.** `app/features/indicators.py` computes EMA/RSI/MACD/
  ATR/Bollinger Bands via `pandas-ta`, which implements all five as standard trailing/causal
  formulas (exponential smoothing, Wilder's smoothing, a rolling mean/std) — none use centered
  windows. Rather than relying on that being true, `test_no_lookahead_indicators_match_when_computed_on_truncated_series`
  recomputes indicators on a truncated series and asserts every value up to the truncation
  point is bit-identical to the value computed with the full series available — i.e. a row's
  indicator value provably cannot have been influenced by rows after it.
- **Row order, not the time index, drives the calculation.** `add_all_indicators` requires the
  input sorted ascending by timestamp and raises otherwise — pandas-ta's rolling/EWM
  calculations operate on row position, so an unsorted input would silently compute nonsense
  (or worse, something that happens to look plausible) rather than fail loudly.
  Real processed data has gaps (weekends, etc. — Phase 3) but no non-monotonic ordering, so
  this doesn't require the time index itself to be evenly spaced, only correctly ordered.
- **Warmup NaNs are left as NaN, not filled or backfilled.** A row before an indicator's
  warmup period has elapsed (e.g. no EMA200 until the 200th bar) has no valid value — and
  filling it with anything (even a "reasonable" guess) would be fabricating information that
  didn't exist at that point in history. On the real Phase 2/3 data this drops roughly 3-4%
  of rows to warmup (e.g. EUR/USD D1: 5,769 -> 5,570 rows with all five indicators valid);
  Phase 5/6 decide whether/how to handle the remaining warmup NaNs when assembling the final
  training set.

## Phase 5 (feature engineering: derived features + multi-timeframe alignment)

- **Bar timestamps are open times, not close times — this is the central hazard.** An H4 bar
  labeled `00:00` spans `00:00`-`04:00` and only "closes" (becomes fully observed) at `04:00`.
  `app.features.multi_timeframe.as_of_join` joins on **close time**
  (`open + app.config.BAR_DURATION[timeframe]`) with a backward-direction `merge_asof`,
  specifically so a target row can never see a same-or-coarser-timeframe bar that hadn't
  actually finished forming yet. Verified concretely by
  `test_as_of_join_only_sees_bars_that_have_actually_closed`, which reproduces exactly this
  00:00-vs-04:00 scenario and asserts the H4 bar is invisible to H1 rows closing before 04:00
  and visible from the instant it (04:00) onward.
- **Symmetric for finer timeframes too.** The spec's multi-timeframe bias includes M15
  direction even when the target is H1 (M15 is finer, not coarser). The same close-time as-of
  join handles this correctly without a separate code path — "most recently closed bar" is
  well-defined regardless of which side is finer.
- **Derived features (EMA ratios, Bollinger width/position, returns) are pure functions of
  already-verified-causal columns** — ratios of Phase 4's indicator outputs, and
  `pct_change()` for returns (which by definition divides by an earlier value). Verified with
  their own no-lookahead truncation test
  (`test_returns_no_lookahead_when_computed_on_truncated_series`), mirroring Phase 4's.
- **Real finding: multi-timeframe bias coverage is honestly sparse for older history**, a
  direct consequence of the M15/H1 data-depth limitation documented in `docs/data_sources.md`.
  On the real EUR/USD D1 feature set (5,769 rows): `M15_direction` is only populated for the
  most recent 59 rows, `H1_direction` for 698, `H4_direction` for 692, while `D1_direction`
  (D1's own) covers 5,720. `mtf_bias`'s majority vote gracefully degrades to whichever
  timeframes actually have data (verified by
  `test_attach_multi_timeframe_bias_majority_vote_and_graceful_degradation`) rather than
  going NaN just because M15/H1 aren't available that far back — but any consumer of
  `mtf_bias` on long-history D1 rows should know it's effectively a 1-2-timeframe vote for
  most of that history, not a true 4-timeframe consensus. This is a data-availability fact,
  not a code bug.
- **Regime and sentiment are deliberately absent from this schema**, not stubbed with NaN
  placeholders — see `data/features/README.md`. Phase 9/10 extend the schema when those
  modules exist, rather than this phase guessing at a shape for data that doesn't exist yet.
## Phase 6 (target generation)

- **The exact leakage boundary, stated precisely**: `target[t]` is a function of exactly
  `close[t]`, `close[t + horizon_bars]`, and `ATR14[t]/close[t]` — nothing else. Verified
  directly by `test_target_depends_only_on_exactly_horizon_bars_ahead`, which builds two
  datasets identical through row `t + horizon_bars` but diverging afterward, and asserts
  `target[t]` is bit-identical between them for every row whose defining window lies entirely
  in the shared prefix.
- **Volatility-adjusted threshold, not a fixed one** — `threshold[t] = volatility_multiplier *
  ATR14[t]/close[t]`, reusing Phase 4's already-verified-causal ATR rather than computing a
  second, redundant volatility measure. A fixed cutoff (e.g. "> 0.1%") would mean something
  completely different for EUR/USD (~0.1-0.5%/day moves) than BTC/USD (several %/day) — using
  each row's own normalized volatility avoids exactly the "arbitrary thresholds and excessive
  class imbalance" risk the spec calls out. Confirmed on the real data: no run out of 12
  (asset x timeframe) came back flagged `is_imbalanced` (dominant class > 80%) — see
  `class_balance_report` in every labeled manifest.
- **Real finding**: HOLD turned out to be the *minority* class everywhere (15-23% across all
  12 real combinations), not the dominant one as might be assumed — at horizon_bars=12 with a
  0.5x-ATR threshold, price moves past the threshold in one direction or the other more often
  than it stays within it. BUY/SELL came out fairly balanced against each other too (e.g. EUR/
  USD D1: BUY 40.5% / HOLD 18.9% / SELL 40.6%). This is a property of the current
  `TARGET.horizon_bars=12, TARGET.volatility_multiplier=0.5` configuration, not a fixed
  outcome — changing either in `app.config.TARGET` will shift this balance, which is exactly
  why both are configurable rather than hardcoded.
- **Horizon is bars, not wall-clock time** — 12 bars of D1 skips weekends automatically
  (gaps aren't rows), giving a "12 trading-bars ahead" horizon rather than a fixed calendar
  span. Intentional, standard TA convention, documented in the module docstring.
- **Trailing rows are NaN, never fabricated.** The last `horizon_bars` rows of every dataset
  have no future bar yet; `target`/`future_return` stay NaN for them (not dropped here, not
  filled) — Phase 7 decides how to handle rows with no target when assembling training data.

## Phase 7 (baseline ML models)

- **`StandardScaler` is fit only on the training split, confirmed by construction.**
  `build_pipelines()` puts `StandardScaler` *inside* each Pipeline (for Logistic Regression
  and SVM); `train_baseline_models()` calls `pipeline.fit(X_train, y_train)` exactly once per
  model, so the scaler's mean/variance are computed only from `X_train` — evaluating on
  `X_test` later calls `.transform()` (reusing those fitted statistics), never `.fit()` again.
  There is no code path in this module that fits anything on test data or the full dataset.
- **No random shuffling.** `chronological_split()` takes the first `TRAIN_FRACTION` of rows in
  time order and raises `ValueError` if the input isn't already sorted ascending — spec
  Section 8's explicit requirement for time-series data.
- **Categorical "UNKNOWN" is an honest placeholder, not a leak.** Converting a NaN
  `M15_direction` (Phase 5: M15 history hasn't started that far back) to the literal string
  "UNKNOWN" before one-hot encoding doesn't smuggle in any future information — it's telling
  the model "this input is unavailable," which is true, rather than imputing a guessed value.
- **Real finding, not a leak**: the best baseline model beat a naive majority-class test-set
  baseline in only 3 of 12 (asset x timeframe) combinations. This does not indicate a leakage
  bug (metrics were computed correctly per the above) — it's a genuine result of evaluating
  with a single chronological split, which conflates model quality with whether the test
  period happened to resemble the training period. See `docs/model_card.md` for the full
  breakdown and why Phase 8's walk-forward validation exists precisely to address this.

## Phase 8 (walk-forward validation)

- **Every window is still trained fresh, with the same fit-on-train-only discipline as Phase
  7** — `run_window()` calls `build_pipelines()` (new, unfitted pipelines) and fits each one
  only on that window's own `train` slice. No state (scaler statistics, tree splits, anything)
  ever carries over from one window to the next, and nothing is ever fit on a window's test
  slice or on data outside that window entirely.
- **Configured (calendar-date) windows vs. auto-generated fallback windows — never silently
  substituted.** `app.config.DEFAULT_WALK_FORWARD_WINDOWS` gives the spec's exact 2021-2025
  example, which fits D1 well but has zero real data for M15 (~60-90 days of history) and
  often too little for H1 (~2 years) — both known limitations from Phase 2/3.
  `resolve_configured_windows` marks a window `applicable` only if both its train and test
  slices meet a minimum row count (`MIN_ROWS_PER_SPLIT = 30`); when *no* configured window is
  applicable, `generate_fallback_windows` builds an expanding-window scheme purely from the
  data that actually exists. Every window in every report carries an explicit
  `"source": "configured"` or `"source": "auto_generated_fallback"` tag — a consumer of the
  report always knows which kind of window produced a given result, rather than the two being
  quietly merged into one undifferentiated "walk-forward result."
- **Using `future_return` to score a prediction after the fact is not leakage** — the model
  never sees it as an input feature (Phase 6/7 keep `future_return`/`target_threshold` out of
  `ALL_FEATURE_COLUMNS`). `compute_trading_metrics` only reads it once a prediction already
  exists, to compute what a trade following that prediction would have returned — the same
  thing any retrospective evaluation of a trading signal does.
- **Trading metrics here are a deliberately simplified diagnostic, not the real backtest** —
  no transaction costs, spread, position sizing, or stop-loss/take-profit, and every trade is
  assumed independently sized (no shared capital across concurrent trades). This is spec
  Section 11's "clearly distinguish ML performance from trading performance" applied at the
  walk-forward level; the realistic version is Phase 12's dedicated backtest engine. Nested
  under `"trading"` in every model's metrics dict specifically so it's never conflated with
  the classification metrics next to it.
- **ROC-AUC is `None`, not a crash or a fabricated value, when it's undefined** — a small
  window's test slice can end up missing one of the three classes entirely, which makes
  one-vs-rest ROC-AUC mathematically undefined. `evaluate_with_roc_auc` catches exactly this
  case and reports `None` (matching the spec's own "ROC-AUC where appropriate" wording) rather
  than raising or silently substituting a placeholder number.

## Phase 9 (market regime detection)

- **Rule-based, not clustering, for the live per-bar feature — a leakage decision, not just a
  simplicity preference.** A clustering model's centroids are normally fit once on a dataset;
  fitting on the *entire* historical series (as is standard practice for KMeans) and then
  using those centroids to label an early row would leak the full dataset's distribution
  (including bars far in the future relative to that row) into a "historical" label. The
  rule-based `classify_regime` avoids this entirely — every input (`trend_strength`,
  `volatility_zscore`, EMA relationships) is a rolling/point-in-time calculation using only
  bars ≤ t, with zero fitting step. `cluster_regimes_exploratory` implements clustering too
  (spec Section 6's "consider... if appropriate"), but its own docstring states plainly that
  it's fit on the whole series and is for retrospective/EDA comparison only — never saved as a
  feature, never consumed by any model. See `notebooks/phase9_regime_detection_eda.ipynb` for
  the comparison itself.
- **Verified, not assumed, no-lookahead**: `test_no_lookahead_regime_matches_when_computed_on_truncated_series`
  recomputes `volatility_zscore`/`trend_strength`/`regime` on a truncated series and asserts
  every value up to the truncation point is bit-identical to the full-series computation —
  the same pattern used for indicators (Phase 4) and derived features (Phase 5).
- **Volatility is checked before trend, an explicit priority, not an accident.** The five
  labels span two different axes (trend direction/strength vs. volatility level) that the spec
  collapses into one categorical variable; `classify_regime` resolves the overlap by checking
  volatility extremes first (see the module docstring for the rationale) — documented so the
  priority order is a visible design decision, not a hidden tie-break.
- **Real finding**: trending regimes (Bullish + Bearish combined) are rare in practice — 1-8%
  of labeled bars across all 12 real combinations, because the rule requires *both* a strong
  trend-strength move *and* full EMA alignment simultaneously. Sideways/Range-Bound dominates
  (43-57%). See the Phase 9 notebook for the full breakdown and a discussion of whether
  `REGIME.trend_strength_threshold` should be revisited.

## Phase 10 (news sentiment)

- **Confirmed, not assumed, that no future article is ever used.** `_windowed_aggregate`
  computes, for each bar's own close time, the mean/count of articles published in
  ``(close_time - window, close_time]`` via `searchsorted` — an article at `close_time + 1s`
  is provably excluded by construction (it sorts after `close_time`, so it falls outside the
  index range `searchsorted` returns). Verified directly by
  `test_attach_sentiment_features_no_lookahead`, and the boundary case (an article published
  at *exactly* the bar's close time, which should count) by
  `test_attach_sentiment_features_exact_close_time_is_visible`.
- **A real windowed-aggregation bug caught before it shipped**: the first implementation
  precomputed each article's own trailing-window aggregate (at *that article's* timestamp)
  and then as-of-joined those values onto bars — which is subtly wrong. A bar far enough past
  an article that the window should have "rolled off" by the *bar's* time would still show
  that article as "in range," because the precomputed value was frozen at the article's own
  (much earlier) timestamp. Caught by
  `test_num_relevant_news_is_zero_not_nan_before_any_coverage_gap`; fixed by computing the
  window relative to each bar's own close time directly (`_windowed_aggregate`'s docstring has
  the full explanation). The same category of bug as Phase 5's close-time hazard, just with
  the added twist of the aggregate itself needing to move with the query point, not just the
  lookup.
- **The sample news dataset is synthetic, documented as such everywhere it's used** — not a
  real historical news archive (a licensed vendor would be required for that; this project
  doesn't have one). See `data/news/README.md` and `docs/data_sources.md` for the full
  rationale; every processed manifest's `sentiment_source` field repeats this so it's never
  silently forgotten downstream.
- **`num_relevant_news` is 0 (a real count) when there's genuinely no news in the window;
  `sentiment_score`/probabilities are NaN when there's nothing to average** — the same
  "count vs. value" NaN distinction as Phase 6/9, not blurred here either.
- **Real finding**: sentiment coverage is honestly sparse and follows the data-depth pattern
  established since Phase 2 — M15 (whose ~60-90 day history overlaps heavily with where the
  sample news is concentrated) gets 31-35% coverage in the 24h short window; D1 (decades of
  history vs. ~3 years of sample news) gets under 1.3%. Documented in `docs/data_sources.md`
  rather than left to look like a bug.
- **Real finding: FinBERT scores linguistic tone, not "good/bad for this asset's price," and
  those can diverge.** One sample headline templated as "negative" — "Gold tumbles on improved
  risk appetite reducing haven demand" — scored `sentiment_score = +0.70` (strongly positive)
  because "improved risk appetite" is genuinely positive economic language, even though the
  same sentence is bearish for gold specifically. Aggregate tone/sentiment_score correlation
  held up well overall (mean +0.61 for positive-templated headlines, -0.70 for negative), but
  this single case is a real, worth-remembering limitation of headline-level financial
  sentiment scoring, not a bug in this project's pipeline.
