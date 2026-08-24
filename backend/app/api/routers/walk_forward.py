"""GET /api/walk-forward/{asset}/{timeframe} -- the full Phase 8 walk-forward validation
report (per-window metrics for all 4 models plus cross-window aggregation)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import AssetKey, Timeframe
from app.services import repository

router = APIRouter(prefix="/walk-forward", tags=["walk-forward"])


@router.get("/{asset}/{timeframe}")
def get_walk_forward(asset: AssetKey, timeframe: Timeframe) -> dict:
    report = repository.latest_walk_forward_report(asset.value, timeframe)
    if report is None:
        raise HTTPException(status_code=404, detail="No walk-forward report found for this combination.")
    return report
