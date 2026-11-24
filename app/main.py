"""FastAPI application entry point for AI Prospect Discovery API."""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.schemas import DiscoveryRequest, DiscoveryResponse, HealthResponse
from app.services.discovery_service import discover_prospects

app = FastAPI(
    title="AI Prospect Discovery API",
    description="API for discovering relevant prospects across multiple platforms using AI",
    version="0.1.0",
)


@app.get(
    "/",
    include_in_schema=False,
    summary="Redirect root to API documentation",
)
def root_redirect() -> RedirectResponse:
    """Redirect root path to interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Service health check",
)
@app.get(
    "/healthz",
    response_model=HealthResponse,
    tags=["Health"],
    include_in_schema=False,
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
async def prospect_discovery(request: DiscoveryRequest) -> DiscoveryResponse:
    """Handle prospect discovery query and return matching prospects."""
    return await discover_prospects(request)
