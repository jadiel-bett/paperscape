from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_body(test_client: TestClient) -> None:
    response = test_client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}
