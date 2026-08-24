# models/

Trained model artifacts, reproducible from `data/features/` + the training scripts — not
hand-edited.

- `{asset}_{timeframe}_{model}_{stamp}.joblib` — one fitted sklearn `Pipeline` per
  (asset, timeframe, model), from Phase 7's baseline training onward. Never overwritten.
- `{asset}_{timeframe}_baseline_comparison_{stamp}.json` — Phase 7's per-model metrics
  (accuracy, precision/recall/F1, confusion matrix) side by side for one asset/timeframe, plus
  the exact train/test split sizes and source feature manifest. See `docs/model_card.md` for
  the honest headline results.
- `{asset}_{timeframe}_walk_forward_{stamp}.json` — Phase 8's walk-forward validation: one
  entry per resolved window (each tagged `"configured"` or `"auto_generated_fallback"` — see
  `docs/leakage_prevention.md`) with full classification metrics (incl. ROC-AUC) and a
  simplified per-window trading diagnostic, plus an `"overall"` mean/std aggregation across
  windows per model. This supersedes the Phase 7 single-split comparison as the primary
  evaluation — the single split still exists as the very first, most naive baseline.
