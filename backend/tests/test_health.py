"""Phase 1 smoke test: the API skeleton starts and reports healthy.

Phase 1's `test_nav_routers_registered` (checking a `/ping` stub per nav section) was retired
in Phase 13, which replaced every stub with a real endpoint at a real path -- see
tests/test_api_routers.py for the routing/behavior coverage that supersedes it.
"""
from fastapi.testclient import TestClient

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
