"""FastAPI application entry point for AI Prospect Discovery API."""

from fastapi import FastAPI

from app.schemas import DiscoveryRequest, DiscoveryResponse, HealthResponse
from app.services.discovery_service import discover_prospects

app = FastAPI(
    title="AI Prospect Discovery API",
    description="API for discovering relevant prospects across multiple platforms using AI",
    version="0.1.0",
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service health check",
)
def health_check() -> HealthResponse:
    """Return application operational health status."""
    return HealthResponse(status="healthy")


@app.post(
    "/prospect-discovery",
    response_model=DiscoveryResponse,
    tags=["Discovery"],
    summary="Discover prospects matching search query",
)
def prospect_discovery(request: DiscoveryRequest) -> DiscoveryResponse:
    """Handle prospect discovery query and return matching prospects."""
    return discover_prospects(request)
