# models/

Trained model artifacts, reproducible from `data/features/` + the training scripts — not
hand-edited.

- `{asset}_{timeframe}_{model}_{stamp}.joblib` — one fitted sklearn `Pipeline` per
  (asset, timeframe, model), from Phase 7's baseline training onward. Never overwritten.
- `{asset}_{timeframe}_baseline_comparison_{stamp}.json` — Phase 7's per-model metrics
  (accuracy, precision/recall/F1, confusion matrix) side by side for one asset/timeframe, plus
  the exact train/test split sizes and source feature manifest. See `docs/model_card.md` for
  the honest headline results.
- Phase 8 will add walk-forward validation runs (multiple windows per asset/timeframe) here
  too, superseding the single-split baseline comparison as the primary evaluation.
