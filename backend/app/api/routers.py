"""API router registry.

Phase 1 note: routers are structural stubs that prove the FastAPI app, its routing table,
and the nav-to-endpoint mapping exist. Real business logic (market analysis, predictions,
explainability, model lab, walk-forward, backtesting, news sentiment) is added feature by
feature in Phase 13, once the underlying services from Phases 2-12 exist. Each stub returns
a small "not implemented yet" payload rather than 404, so the frontend nav can be wired up
against a real (if empty) API from the start.
"""
from __future__ import annotations

from fastapi import APIRouter

NOT_YET_IMPLEMENTED = {"status": "not_implemented", "note": "Implemented in a later phase."}

auth_router = APIRouter(prefix="/auth", tags=["auth"])
market_analysis_router = APIRouter(prefix="/market-analysis", tags=["market-analysis"])
predictions_router = APIRouter(prefix="/predictions", tags=["predictions"])
explainability_router = APIRouter(prefix="/explainability", tags=["explainability"])
model_lab_router = APIRouter(prefix="/model-lab", tags=["model-lab"])
walk_forward_router = APIRouter(prefix="/walk-forward", tags=["walk-forward"])
backtesting_router = APIRouter(prefix="/backtesting", tags=["backtesting"])
news_sentiment_router = APIRouter(prefix="/news-sentiment", tags=["news-sentiment"])

_ALL_ROUTERS = (
    auth_router,
    market_analysis_router,
    predictions_router,
    explainability_router,
    model_lab_router,
    walk_forward_router,
    backtesting_router,
    news_sentiment_router,
)


def _stub(router: APIRouter) -> None:
    @router.get("/ping")
    def ping() -> dict:  # noqa: ANN202 - simple stub
        return {**NOT_YET_IMPLEMENTED, "router": router.prefix}


for _router in _ALL_ROUTERS:
    _stub(_router)


def register_routers(app) -> None:  # noqa: ANN001 - FastAPI app, avoids circular import
    for router in _ALL_ROUTERS:
        app.include_router(router, prefix="/api")
