# data/features/

Engineered feature sets built from `data/processed/`, one parquet + manifest per
(asset, timeframe), never overwritten (same convention as `data/raw/` and `data/processed/`).
Every column is computed using only information available at that row's timestamp — see
`docs/leakage_prevention.md`.

**Current schema** (`backend/app/features/feature_engineering.py::FEATURE_COLUMNS`):
- The five indicators (Phase 4): `EMA20/50/200`, `RSI14`, `MACD`/`MACD_signal`/`MACD_histogram`,
  `ATR14`, `BB_lower`/`BB_middle`/`BB_upper`
- Derived/relationship features (Phase 5): `EMA20_to_EMA50`, `EMA50_to_EMA200`, `BB_width`,
  `BB_position`, `return_1`/`return_3`/`return_6`/`return_12`
- Multi-timeframe bias (Phase 5): `M15_direction`/`H1_direction`/`H4_direction`/`D1_direction`
  (each an as-of lookup, never peeking at a not-yet-closed bar — see
  `docs/leakage_prevention.md`'s Phase 5 entry) and the majority-vote `mtf_bias`

- Target label (Phase 6, `backend/app/ml/target.py`): `future_return`, `target_threshold`,
  and `target` (BUY/HOLD/SELL) — see `docs/leakage_prevention.md`'s Phase 6 entry for the
  exact leakage boundary. **"Latest" file per (asset, timeframe) is always the most complete
  one** — once Phase 6 runs, the latest file includes the target; a consumer just wants
  whatever's newest, same convention as `data/raw/`/`data/processed/`.

- Market regime (Phase 9, `backend/app/regime/detector.py`): `volatility_zscore`,
  `trend_strength`, and `regime` (one of Bullish Trending / Bearish Trending /
  Sideways-Range-Bound / High Volatility / Low Volatility) — rule-based, not clustering, for
  this live feature; see `docs/leakage_prevention.md`'s Phase 9 entry for why. Real
  distribution across all 12 combos: Sideways dominates (43-57%), Trending is rare (1-8%
  combined) — see `notebooks/phase9_regime_detection_eda.ipynb`.

- News sentiment (Phase 10, `backend/app/sentiment/pipeline.py`): `sentiment_score`,
  `positive_probability`, `negative_probability`, `neutral_probability`, `num_relevant_news`,
  `rolling_sentiment_score` — from the real `ProsusAI/finbert` model scoring a documented
  *synthetic sample* news dataset (not a real historical archive; see `data/news/README.md`),
  joined timestamp-aware (never a future article). Coverage is honestly sparse outside recent
  history (0.6-1.3% on D1, 31-35% on M15) — see `docs/data_sources.md` for the full table and
  why. This is currently the last stage in the pipeline, so "latest file" now means
  indicators + derived + MTF bias + target + regime + sentiment, all in one dataset.

Every manifest's `source_processed_manifests` (or, for downstream files, `source_features_manifest`)
traces back to the exact upstream file(s) used to build it — full provenance chain back to the
original raw pull.
