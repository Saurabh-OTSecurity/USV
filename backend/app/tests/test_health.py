from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_healthy_when_database_reachable():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "usv-backend",
        "database": "healthy",
    }


def test_health_returns_degraded_when_database_unreachable():
    with TestClient(app) as client:
        with patch("app.api.routes.health.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception("connection refused")
            response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "service": "usv-backend",
        "database": "unavailable",
    }
