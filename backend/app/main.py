"""FastAPI application entrypoint.

Phase 1 scope: app instantiation, CORS, a real ``/health`` check, and router registration
for the nav sections defined in the spec (Section 13). No business logic yet.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import register_routers
from app.config import NOT_LIVE_TRADING_DISCLAIMER, SETTINGS

app = FastAPI(
    title="AI-Powered Multi-Asset Market Intelligence & Explainable Trading Signal Prediction Platform",
    description=NOT_LIVE_TRADING_DISCLAIMER,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
