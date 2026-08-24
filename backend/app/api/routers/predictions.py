"""GET /api/predictions/{asset}/{timeframe} -- latest BUY/HOLD/SELL prediction from each of the
4 models plus consensus (spec Section 9's model-disagreement example)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import AssetKey, Timeframe
from app.services import repository

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/{asset}/{timeframe}")
def get_predictions(asset: AssetKey, timeframe: Timeframe) -> dict:
    try:
        return repository.predictions_with_consensus(asset.value, timeframe)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
