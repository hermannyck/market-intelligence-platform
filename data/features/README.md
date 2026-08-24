# data/features/

Engineered feature sets (indicators, multi-timeframe features, regime, sentiment) built
from `data/processed/`. Every column is computed using only information available at that
row's timestamp — see `docs/leakage_prevention.md`.

**Phase 4** added the indicator *computation* module (`backend/app/features/indicators.py` —
EMA/RSI/MACD/ATR/Bollinger Bands), but doesn't persist a standalone dataset here yet: it's
verified directly against `data/processed/` via tests and a real-data smoke check. **Phase 5**
assembles the actual feature sets that land in this directory — indicator outputs plus the
derived/relationship features (EMA20_to_EMA50, BB_width, BB_position, returns,
multi-timeframe, regime, sentiment).
