"""SQLAlchemy ORM models. Phase 13: just `User`, for the auth gate the user chose to keep
(spec itself never requires accounts — see docs/architecture.md's locked-in decisions).

Deliberately DB-agnostic column types (plain auto-incrementing integer PK, no Postgres-specific
types like UUID) so the same model works unchanged against both the documented production
target (PostgreSQL, `app.config.SETTINGS.database_url`) and a local SQLite file — see
`docs/architecture.md`'s Phase 13 entry for why SQLite is used for local development in this
environment (Docker/PostgreSQL aren't installed in this sandbox).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
