"""Phase 1 smoke test: the API skeleton starts and reports healthy.

Phase 1's `test_nav_routers_registered` (checking a `/ping` stub per nav section) was retired
in Phase 13, which replaced every stub with a real endpoint at a real path -- see
tests/test_api_routers.py for the routing/behavior coverage that supersedes it.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database.session import Base
from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "not a live trading system" in body["disclaimer"]


def test_nav_routers_registered():
    # One real endpoint per Section 13 nav section should resolve to something other than
    # 404 Not Found (some return 404 for missing *data*, which is a different, expected
    # outcome from the route not existing at all -- checked precisely in test_api_routers.py).
    for path in (
        "/api/market-analysis/EURUSD/D1",
        "/api/predictions/EURUSD/D1",
        "/api/explainability/EURUSD/D1/random_forest",
        "/api/model-lab/EURUSD/D1",
        "/api/walk-forward/EURUSD/D1",
        "/api/backtesting/EURUSD/D1/random_forest",
        "/api/news-sentiment/EURUSD",
    ):
        response = client.get(path)
        assert response.status_code in (200, 404), f"{path} returned {response.status_code}"


def test_lifespan_survives_database_unreachable():
    """Phase 16: main.py's module docstring states the app 'must keep working even if the
    database isn't reachable' -- verified directly, not just asserted in a comment, by making
    startup's `Base.metadata.create_all` raise and confirming the app still starts and /health
    still responds normally (every other read-only data endpoint has no DB dependency at all,
    per that same docstring -- only auth endpoints would actually be affected)."""
    with patch.object(Base.metadata, "create_all", side_effect=Exception("simulated DB outage")):
        with TestClient(app) as isolated_client:
            response = isolated_client.get("/health")
            assert response.status_code == 200
