"""Unit and integration tests for API routes."""

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_health_route() -> None:
    """Verify GET /health returns 200 with status 'healthy'."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_prospect_discovery_route() -> None:
    """Verify POST /prospect-discovery returns 200 with expected response structure."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {"query": "AI founders in San Francisco"}
        response = await client.post("/prospect-discovery", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["query"] == "AI founders in San Francisco"
        assert data["total_prospects"] == 0
        assert data["prospects"] == []


@pytest.mark.asyncio
async def test_prospect_discovery_empty_query() -> None:
    """Verify POST /prospect-discovery validates required query field."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/prospect-discovery", json={"query": ""})
        assert response.status_code == 422
