"""Discovery service orchestrator for candidate prospect retrieval."""

from app.schemas import DiscoveryRequest, DiscoveryResponse


def discover_prospects(request: DiscoveryRequest) -> DiscoveryResponse:
    """Orchestrate prospect discovery for a validated search request.

    Args:
        request: The validated user discovery query request.

    Returns:
        DiscoveryResponse containing discovery status, query, and prospects list.
    """
    return DiscoveryResponse(
        success=True,
        query=request.query,
        total_prospects=0,
        prospects=[],
    )
