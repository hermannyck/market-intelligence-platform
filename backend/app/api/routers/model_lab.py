"""GET /api/model-lab/{asset}/{timeframe} -- baseline comparison (Phase 7) + walk-forward
summary (Phase 8) for all 4 models side by side, supporting model disagreement/consensus
comparisons (spec Section 9)."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import AssetKey, Timeframe
from app.services import repository

router = APIRouter(prefix="/model-lab", tags=["model-lab"])


@router.get("/{asset}/{timeframe}")
def get_model_lab(asset: AssetKey, timeframe: Timeframe) -> dict:
    return repository.model_lab(asset.value, timeframe)
