"""FastAPI application entrypoint.

Phase 1: app instantiation, CORS, a real ``/health`` check, router registration.
Phase 13: real endpoints behind those routers, backed by the files Phases 2-12 produce (see
``app.services.repository``), plus a real login gate (``app.api.routers.auth``) against a
``users`` table. Table creation on startup is best-effort and never fatal -- the app (and
every read-only data endpoint) must keep working even if the database isn't reachable, exactly
as Phase 1 designed ``app/database/session.py`` to allow.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import register_routers
from app.config import NOT_LIVE_TRADING_DISCLAIMER, SETTINGS
from app.database.session import Base, engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    import app.database.models  # noqa: F401 - registers User on Base.metadata before create_all

    try:
        Base.metadata.create_all(bind=engine)
    except Exception:  # noqa: BLE001 - any DB error here must not take the whole API down
        logger.warning(
            "Database not reachable at startup (DATABASE_URL=%s) -- auth endpoints will fail "
            "until it is, but every other endpoint (market data, predictions, etc.) still works.",
            SETTINGS.database_url,
        )
    yield


app = FastAPI(
    title="AI-Powered Multi-Asset Market Intelligence & Explainable Trading Signal Prediction Platform",
    description=NOT_LIVE_TRADING_DISCLAIMER,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(SETTINGS.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routers(app)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "environment": SETTINGS.environment,
        "disclaimer": NOT_LIVE_TRADING_DISCLAIMER,
    }
