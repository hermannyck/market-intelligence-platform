# Model card — Phase 7 baseline

**This is not financial advice and does not indicate a profitable trading system.** These are
the honest results of the first, simplest possible evaluation (a single chronological
train/test split) across all 12 (asset × timeframe) combinations. Read alongside
`docs/leakage_prevention.md` and Phase 8's walk-forward validation (a much more robust read
than what's below — a single split can't distinguish "the model is good" from "the test
period happened to suit it").

## Setup

- **Models**: Logistic Regression, Random Forest, SVM, XGBoost — each a single sklearn
  `Pipeline` (`backend/app/ml/models.py::build_pipelines`)
- **Split**: chronological, 80% train / 20% test, no shuffling (spec Section 8's explicit
  requirement for time-series data)
- **Features**: the 19 numeric indicator/derived columns (Phase 4-5) + 5 one-hot-encoded
  multi-timeframe direction columns
- **Target**: BUY/HOLD/SELL from Phase 6 (horizon=12 bars, 0.5× ATR-based threshold)

## Headline result: accuracy clusters near chance, and often *below* a naive baseline

| Asset | Timeframe | Train / Test rows | Best model | Best accuracy | Majority-class baseline | Beat baseline? |
|---|---|---|---|---|---|---|
| BTC/USD | D1  | 3,319 / 830   | SVM | 0.387 | 0.413 | No |
| BTC/USD | H1  | 13,687 / 3,422 | Logistic Regression | 0.394 | 0.419 | No |
| BTC/USD | H4  | 3,291 / 823   | XGBoost | 0.434 | 0.436 | No |
| BTC/USD | M15 | 4,336 / 1,085 | SVM | 0.473 | 0.465 | **Yes** |
| EUR/USD | D1  | 4,446 / 1,112 | SVM | 0.406 | 0.415 | No |
| EUR/USD | H1  | 13,638 / 3,410 | SVM | 0.430 | 0.442 | No |
| EUR/USD | H4  | 3,189 / 798   | Random Forest | 0.484 | 0.441 | **Yes** |
| EUR/USD | M15 | 4,352 / 1,089 | XGBoost | 0.443 | 0.465 | No |
| XAU/USD | D1  | 4,693 / 1,174 | SVM | 0.405 | 0.505 | No |
| XAU/USD | H1  | 10,836 / 2,710 | Random Forest | 0.397 | 0.430 | No |
| XAU/USD | H4  | 2,212 / 554   | Logistic Regression | 0.359 | 0.448 | No |
| XAU/USD | M15 | 3,453 / 864   | SVM | 0.464 | 0.446 | **Yes** |

**The best model beat a naive "always predict the test period's majority class" baseline in
only 3 of 12 combinations.** ("Majority-class baseline" here means: look at the actual class
distribution of the test period and always predict whichever of BUY/HOLD/SELL was most
common — not a fixed 33% chance line, since Phase 6 already showed the classes aren't
balanced 33/33/33.)

Full per-model metrics (precision/recall/F1, confusion matrices) are in
`models/{asset}_{timeframe}_baseline_comparison_*.json`.

## Why this isn't surprising, and why it doesn't end the project here

1. **A single chronological split conflates "model quality" with "did this one test period
   happen to resemble the training period."** XAU/USD D1's majority baseline is 50.5% —
   meaning the test period was unusually one-sided (mostly BUY) compared to training, which a
   model trained on a different-looking earlier regime has no way to have learned. This is
   precisely the failure mode walk-forward validation (Phase 8, multiple expanding windows) is
   designed to reveal and average out, rather than one lucky-or-unlucky split.
2. **Financial markets are close to informationally efficient** at these horizons using only
   price/indicator history — near-chance accuracy on a 3-class problem is a well-documented,
   unsurprising result in this kind of research (consistent with what similar prior projects
   in this workspace found: EUR/USD accuracy "near 33% chance baseline" — see
   `docs/architecture.md`'s "lessons carried over" section). It is not evidence of a bug.
3. **This is exactly why the project's own scope explicitly refuses to claim predictive
   guarantees** (spec Section 23) and prioritizes explainability/evaluation robustness over a
   headline accuracy number.

## What Phase 7 deliberately does not attempt

- No hyperparameter tuning (Section 8 allows GridSearchCV/RandomizedSearchCV respecting
  time-series structure — that's a Phase 8+ refinement once walk-forward validation exists to
  tune against, not before).
- No claim about which of the 4 models is "best" — a single split's ranking is not reliable
  enough to draw that conclusion (see point 1 above); Experiment 1 (spec Section 20) revisits
  this properly once Phase 8 exists.

## Phase 8 update — walk-forward validation (a more trustworthy read than the above)

Ran `backend/app/validation/walk_forward.py` on all 12 combinations. Window counts varied by
how much real history exists per timeframe (see `docs/leakage_prevention.md`): D1 got all 4
configured 2021-2025 windows for every asset; H1/H4 mostly resolved to just 1 configured
window (only ~2 years of H1/H4 history exists); M15 always fell back to 4 auto-generated
windows (no real data before ~mid-2026). Full reports:
`models/{asset}_{timeframe}_walk_forward_*.json`.

**Accuracy is still near chance across the board** — same conclusion as Phase 7, now on more
robust multi-window evidence: most model/asset/timeframe combinations land in the 0.30-0.43
range.

**One standout, reported with appropriate caution**: XAU/USD D1's SVM averaged **0.510
accuracy across all 4 windows with a low std (0.035)** — i.e. consistently better than chance
across 2022, 2023, 2024, and 2025 individually (0.466 / 0.508 / 0.504 / 0.563), not a fluke
from one lucky window. This is the single most interesting result in the baseline+walk-forward
work so far and is worth investigating further (SHAP explainability, Phase 11, is the natural
next step to understand *why*) — but four ~250-row test windows is still a small evidence
base, and gold's multi-year trending behavior over this specific historical period may not
generalize.

**A statistical footgun, caught and worth stating explicitly**: BTC/USD's H1 and H4 combinations
show `accuracy_std = 0.0` in the aggregated report. This is **not** evidence of stability — it's
an artifact of only 1 configured window having enough data to resolve for those combinations
(`n_windows=1`), so "std across windows" is the standard deviation of a single number, which is
trivially zero. Any consumer of `overall.*.accuracy_std` must check `accuracy_n_windows` first;
a std computed from 1 window means nothing.

**The simplified trading diagnostic overstates real profitability, on purpose, as a
demonstration of why Phase 12 exists.** XAU/USD D1's SVM windows average a 60% simulated win
rate and a **815% mean cumulative return** — which is not a realistic number. The diagnostic
(spec Section 11) assumes zero transaction costs, no spread, no position sizing, and full
reinvestment of an ever-growing position on every trade; it also shows a -65% average maximum
drawdown even in this rosy simulation, meaning the equity curve implied here is far more
volatile than the headline return suggests. This is exactly the gap between "ML performance"
and "trading performance" the spec asks to be kept explicitly distinct — the realistic version,
with costs, sizing, and drawdown-aware risk management, is Phase 12's dedicated backtest
engine, not this diagnostic.

## Phase 11 update — SHAP explainability (a look inside the XAU/USD D1 SVM standout)

Ran `backend/app/explainability/pipeline.py` on all 48 (asset × timeframe × model)
combinations. Full reports: `models/{asset}_{timeframe}_{model}_explainability_*.json`.

**A real, concrete local explanation** (spec Section 12's exact example format) for XAU/USD
D1's SVM — the Phase 8 standout — at its most recent row (2026-08-06):

```
Prediction: HOLD
Probability: SELL 27.8%  HOLD 38.0%  BUY 34.2%
Top factors:
BB_middle    +0.0472
EMA50        +0.0383
EMA200       +0.0255
BB_upper     +0.0251
EMA20        +0.0248
```

Notice the probabilities are fairly close together (28/38/34%) — this particular prediction
isn't a confident call, which is honest and consistent with the model's ~51% overall accuracy
on this combination (Phase 8): a real edge over chance, not a reliably confident one.

**Cross-combination pattern**: `EMA200` (and the closely-related `EMA50`, `EMA20`) and
Bollinger Band levels (`BB_upper`/`BB_middle`/`BB_lower`) dominate the top-5 global feature
importance list across nearly all 48 combinations, for every model type. This makes intuitive
sense — `EMA200` tracks a long trailing price level, so it (and where price sits relative to
the Bollinger Bands) is highly informative about "where is price relative to its own recent
history," a natural strong signal regardless of model family. Multi-timeframe direction
columns and news sentiment rarely crack the top 5 (an exception: SVM models on H1/H4 lean more
on `D1_direction`/`H4_direction` than the other models do) — consistent with Phase 5's finding
that multi-timeframe coverage itself is sparse for older history, and Phase 10's finding that
sentiment coverage is sparse everywhere except recent M15 history.

## Phase 12 update — the real backtest engine (Phase 8's diagnostic, corrected)

Ran `backend/app/backtesting/pipeline.py` on all 48 combinations, driven by genuinely
out-of-sample walk-forward predictions (never the true label — see
`docs/leakage_prevention.md`'s Phase 12 entry). Full reports:
`models/{asset}_{timeframe}_{model}_backtest_*.json`.

**Headline result: only 6 of 48 combinations were net profitable once real transaction costs,
spread, and ATR-based stop-loss/take-profit are simulated.** The other 42 lost money over
their walk-forward test period. Losses are heaviest on the highest-frequency timeframes
(M15/H1 generate hundreds to ~1,500 trades per combination — e.g. EUR/USD H1 lost ~14-15%
across all 4 models), where transaction costs compound over many small trades; D1/H4 (fewer,
larger trades) fared noticeably better.

**The XAU/USD D1 SVM standout, before and after realistic costs — the clearest illustration
in this whole project of why Phase 8's diagnostic needed a Phase 12 to correct it:**

| Metric | Phase 8 simplified diagnostic | Phase 12 real backtest |
|---|---|---|
| Win rate | 60.2% | 43.0% |
| Profit factor | 1.70 | 1.22 |
| Total / mean cumulative return | **+815%** (mean across windows) | **+2.9%** |
| Max drawdown | -65.4% | -2.8% |
| Sharpe ratio (trade-level) | 0.19 | 0.09 |

The real engine still finds a genuine, small edge (profit factor > 1, positive total return)
— it isn't that the earlier finding was fake, it's that the earlier diagnostic's zero-cost,
full-notional, no-stop-loss assumptions inflated an honest small edge into a fantastical
headline number. This is exactly the "clearly distinguish ML performance from trading
performance" the spec asks for (Section 11), made concrete with real numbers rather than
asserted abstractly.

**A handful of real bright spots** worth naming: BTC/USD H4 (Random Forest +3.2%, XGBoost
+4.7%), XAU/USD D1 (Logistic Regression +4.6%, SVM +2.9%). All six profitable combinations sit
on H4 or D1 — none on M15 or H1, reinforcing the transaction-cost-drag pattern above.
