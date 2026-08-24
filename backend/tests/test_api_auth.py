"""Phase 13 tests for the real /api/auth endpoints -- register/login/me against an in-memory
SQLite database (overriding get_db), not the configured production DATABASE_URL."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.database import models  # noqa: F401 - registers User on Base.metadata
from app.database.session import Base
from app.main import app


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_disclaimer_is_unauthenticated(client):
    response = client.get("/api/auth/disclaimer")
    assert response.status_code == 200
    assert "not a live trading system" in response.json()["disclaimer"]


def test_register_then_me_with_returned_token(client):
    register = client.post("/api/auth/register", json={"email": "user@example.com", "password": "supersecret1"})
    assert register.status_code == 201
    token = register.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_register_duplicate_email_conflicts(client):
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": "supersecret1"})
    second = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "anotherpass1"})
    assert second.status_code == 409


def test_login_success_and_wrong_password(client):
    client.post("/api/auth/register", json={"email": "user2@example.com", "password": "correctpass1"})

    good = client.post("/api/auth/login", json={"email": "user2@example.com", "password": "correctpass1"})
    assert good.status_code == 200
    assert "access_token" in good.json()

    bad = client.post("/api/auth/login", json={"email": "user2@example.com", "password": "wrongpass1"})
    assert bad.status_code == 401


def test_me_without_token_is_unauthorized(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_is_unauthorized(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_register_rejects_short_password(client):
    response = client.post("/api/auth/register", json={"email": "user3@example.com", "password": "short"})
    assert response.status_code == 422
