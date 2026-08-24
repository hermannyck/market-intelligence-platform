"""GET /api/market-analysis/{asset}/{timeframe} -- OHLCV + the five indicators, multi-timeframe
bias, and market regime info for the dashboard/market-analysis page (spec Sections 2, 6, 14)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import AssetKey, Timeframe
from app.services import repository

router = APIRouter(prefix="/market-analysis", tags=["market-analysis"])


@router.get("/{asset}/{timeframe}")
def get_market_analysis(asset: AssetKey, timeframe: Timeframe, limit: int = 200) -> dict:
    try:
        return repository.market_analysis(asset.value, timeframe, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
