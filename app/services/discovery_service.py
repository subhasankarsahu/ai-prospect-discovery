"""Discovery service orchestrator for candidate prospect retrieval."""

import logging

from fastapi import HTTPException, status

from app.schemas import DiscoveryRequest, DiscoveryResponse
from app.services.llm_service import (
    BaseLLMService,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMServiceError,
    LLMTimeoutError,
    get_llm_service,
)

logger = logging.getLogger(__name__)


async def discover_prospects(
    request: DiscoveryRequest,
    llm_service: BaseLLMService | None = None,
) -> DiscoveryResponse:
    """Orchestrate prospect discovery for a validated search request.

    Args:
        request: The validated user discovery query request.
        llm_service: Optional LLM provider instance; defaults to the configured singleton.

    Returns:
        DiscoveryResponse containing discovery status, query, and prospects list.

    Raises:
        HTTPException: With corresponding HTTP status code on upstream failures.
    """
    service = llm_service or get_llm_service()

    try:
        intent = await service.extract_query_intent(request.query)
    except LLMRateLimitError as exc:
        logger.warning("LLM rate limit error during query discovery: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM provider rate limit exceeded",
        ) from exc
    except LLMTimeoutError as exc:
        logger.error("LLM timeout during query discovery: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM provider request timed out",
        ) from exc
    except LLMResponseParsingError as exc:
        logger.error("LLM response parsing error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to parse LLM intent response",
        ) from exc
    except LLMConfigurationError as exc:
        logger.error("LLM configuration error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider service is not properly configured",
        ) from exc
    except LLMServiceError as exc:
        logger.error("General LLM service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM provider error",
        ) from exc

    if not intent.is_prospect_query:
        logger.info("Query '%s' classified as non-prospect intent", request.query)
        return DiscoveryResponse(
            success=True,
            query=request.query,
            total_prospects=0,
            prospects=[],
        )

    # Note: Platform integrations will be invoked here in subsequent phases.
    return DiscoveryResponse(
        success=True,
        query=request.query,
        total_prospects=0,
        prospects=[],
    )
