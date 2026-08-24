"""Phase 1 smoke test: the API skeleton starts and reports healthy."""
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
    # One stub endpoint per Section 13 nav item should resolve (not 404), proving the
    # routing table matches the spec's navigation even though logic isn't implemented yet.
    for prefix in (
        "market-analysis", "predictions", "explainability", "model-lab",
        "walk-forward", "backtesting", "news-sentiment",
    ):
        response = client.get(f"/api/{prefix}/ping")
        assert response.status_code == 200
        assert response.json()["status"] == "not_implemented"
