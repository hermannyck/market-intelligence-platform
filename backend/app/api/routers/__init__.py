"""Phase 13: real routers, one per spec Section 13 nav item (Dashboard is frontend-composed
from these, same as planned in Phase 1's scaffold -- there's no dedicated dashboard endpoint)."""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routers import (
    auth,
    backtesting,
    explainability,
    market_analysis,
    model_lab,
    news_sentiment,
    predictions,
    walk_forward,
)

_ALL_ROUTERS = (
    auth.router,
    market_analysis.router,
    predictions.router,
    explainability.router,
    model_lab.router,
    walk_forward.router,
    backtesting.router,
    news_sentiment.router,
)


def register_routers(app: FastAPI) -> None:
    for router in _ALL_ROUTERS:
        app.include_router(router, prefix="/api")
