"""Discovery service orchestrator for candidate prospect retrieval."""

from app.schemas import DiscoveryRequest, DiscoveryResponse, Prospect, SocialLink


def discover_prospects(request: DiscoveryRequest) -> DiscoveryResponse:
    """Orchestrate prospect discovery for a validated search request.

    Args:
        request: The validated user discovery query request.

    Returns:
        DiscoveryResponse containing discovery status, query, and prospects list.
    """
    placeholder_prospect = Prospect(
        name="Sample Prospect",
        location="San Francisco, CA, USA",
        social_link=[
            SocialLink(
                platform="linkedin",
                link="https://www.linkedin.com/in/sample-prospect",
            )
        ],
    )
    return DiscoveryResponse(
        success=True,
        query=request.query,
        total_prospects=1,
        prospects=[placeholder_prospect],
    )
