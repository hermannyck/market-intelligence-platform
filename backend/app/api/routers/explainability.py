"""GET /api/explainability/{asset}/{timeframe}/{model} -- the latest SHAP global/local
explanation report (Phase 11)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import AssetKey, ModelName, Timeframe
from app.services import repository

router = APIRouter(prefix="/explainability", tags=["explainability"])


@router.get("/{asset}/{timeframe}/{model}")
def get_explainability(asset: AssetKey, timeframe: Timeframe, model: ModelName) -> dict:
    report = repository.latest_explainability_report(asset.value, timeframe, model)
    if report is None:
        raise HTTPException(status_code=404, detail="No explainability report found for this combination.")
    return report
