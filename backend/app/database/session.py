"""SQLAlchemy engine/session setup (PostgreSQL).

Phase 1 note: this wires the plumbing only. No ORM models exist yet (later phases add
tables for OHLCV data, predictions, backtest runs, etc. under ``app/models``). The FastAPI
app does not require a live database connection to start or to serve ``/health`` — the
engine is created lazily via ``get_session`` so Phase 1 verification doesn't need Postgres
running.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import SETTINGS

engine = create_engine(SETTINGS.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models added in later phases."""


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
