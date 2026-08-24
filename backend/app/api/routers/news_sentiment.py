"""GET /api/news-sentiment/{asset} -- scored sample-news headlines for the news sentiment
timeline (Phase 10). Not asset+timeframe scoped -- news isn't timeframe-specific."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import AssetKey
from app.services import repository

router = APIRouter(prefix="/news-sentiment", tags=["news-sentiment"])


@router.get("/{asset}")
def get_news_sentiment(asset: AssetKey, limit: int = 100) -> dict:
    return repository.news_sentiment(asset.value, limit=limit)
