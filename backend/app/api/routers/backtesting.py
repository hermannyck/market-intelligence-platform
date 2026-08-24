"""GET /api/backtesting/{asset}/{timeframe}/{model} -- the real Phase 12 backtest (trade log,
equity curve, summary) plus performance-by-regime (spec Section 6's dashboard requirement,
derived from the saved trade log joined against the regime column -- see
app.services.repository's module docstring for why this isn't recomputed live)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import AssetKey, ModelName, Timeframe
from app.services import repository

router = APIRouter(prefix="/backtesting", tags=["backtesting"])


@router.get("/{asset}/{timeframe}/{model}")
def get_backtest(asset: AssetKey, timeframe: Timeframe, model: ModelName) -> dict:
    report = repository.latest_backtest_report(asset.value, timeframe, model)
    if report is None:
        raise HTTPException(status_code=404, detail="No backtest report found for this combination.")
    return report


@router.get("/{asset}/{timeframe}/{model}/performance-by-regime")
def get_performance_by_regime(asset: AssetKey, timeframe: Timeframe, model: ModelName) -> dict:
    result = repository.model_performance_by_regime(asset.value, timeframe, model)
    if result is None:
        raise HTTPException(
            status_code=404, detail="No backtest trades or regime data available for this combination."
        )
    return result
