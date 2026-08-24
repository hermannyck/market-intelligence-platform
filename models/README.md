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
- `{asset}_{timeframe}_{model}_explainability_{stamp}.json` — Phase 11's SHAP output: global
  feature importance (mean |SHAP value| across a sampled set of rows) and a local explanation
  for the most recent row (predicted class, per-class probabilities, top contributing
  features with signed SHAP values) — see `docs/leakage_prevention.md`'s Phase 11 entry for
  the explainer choice per model (TreeExplainer for RF/XGBoost, LinearExplainer for LR,
  KernelExplainer for SVM) and why SVM's explanations are capped to a small sample size.
- `{asset}_{timeframe}_{model}_backtest_{stamp}.json` — Phase 12's real backtest: initial
  capital, position sizing, transaction costs, spread, and ATR-based stop-loss/take-profit
  (all under `backtest_config`), the resulting trade log, a per-bar equity curve, and a
  `summary` (total return, win rate, profit factor, Sharpe ratio, max drawdown, trade count,
  average trade return). Driven entirely by `app.validation.walk_forward.generate_oos_predictions`
  (genuinely out-of-sample — never the true `target`) — see `docs/leakage_prevention.md`'s
  Phase 12 entry. This is the realistic counterpart to Phase 8's simplified trading
  diagnostic, which already showed why costs/sizing/risk management matter.
