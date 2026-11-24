"""Unit and integration tests for API routes."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_route() -> None:
    """Verify GET /health returns 200 with status 'healthy'."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "healthy"}


def test_prospect_discovery_route() -> None:
    """Verify POST /prospect-discovery returns 200 with expected response structure."""
    payload = {"query": "AI founders in San Francisco"}
    response = client.post("/prospect-discovery", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["query"] == "AI founders in San Francisco"
    assert data["total_prospects"] >= 1
    assert len(data["prospects"]) == data["total_prospects"]
    assert "name" in data["prospects"][0]
    assert "social_link" in data["prospects"][0]


def test_prospect_discovery_empty_query() -> None:
    """Verify POST /prospect-discovery validates required query field."""
    response = client.post("/prospect-discovery", json={"query": ""})
    assert response.status_code == 422
