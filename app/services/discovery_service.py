"""Discovery service orchestrator for candidate prospect retrieval."""

import asyncio
import logging
from collections.abc import Sequence

from fastapi import HTTPException, status

from app.platforms import get_all_platform_sources
from app.platforms.base import PlatformSource
from app.schemas import DiscoveryRequest, DiscoveryResponse, QueryIntent
from app.schemas_internal import PlatformOutcome, RawCandidate
from app.services.llm_service import (
    BaseLLMService,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMServiceError,
    LLMTimeoutError,
    get_llm_service,
)
from app.services.search_service import (
    SearchConfigurationError,
    SearchRateLimitError,
    SearchServiceError,
    SearchTimeoutError,
    TavilySearchService,
)

logger = logging.getLogger(__name__)

CONCURRENT_PLATFORM_SEARCH_LIMIT = 3


async def _execute_platform_search(
    platform: PlatformSource,
    intent: QueryIntent,
    search_service: TavilySearchService,
    semaphore: asyncio.Semaphore,
) -> PlatformOutcome:
    """Execute search for a single platform under concurrency control and return a structured outcome."""
    try:
        query = platform.build_query(intent)
        async with semaphore:
            results = await search_service.search(
                query=query,
                include_domains=platform.allowed_domains,
            )

        candidates = [
            RawCandidate(
                source_platform=platform.name,
                canonical_url=platform.extract_canonical_url(r.url),
                title=r.title,
                snippet=r.snippet,
                search_query=query,
            )
            for r in results
            if platform.is_profile_url(r.url)
        ]
        return PlatformOutcome(
            platform_name=platform.name,
            success=True,
            candidates=candidates,
        )
    except asyncio.CancelledError:
        raise
    except SearchRateLimitError as exc:
        logger.warning("Platform %s rate limit exceeded", platform.name)
        return PlatformOutcome(
            platform_name=platform.name,
            success=False,
            error_type="SearchRateLimitError",
            error_message=str(exc),
        )
    except SearchTimeoutError as exc:
        logger.warning("Platform %s request timed out", platform.name)
        return PlatformOutcome(
            platform_name=platform.name,
            success=False,
            error_type="SearchTimeoutError",
            error_message=str(exc),
        )
    except SearchConfigurationError as exc:
        logger.error("Platform %s configuration error", platform.name)
        return PlatformOutcome(
            platform_name=platform.name,
            success=False,
            error_type="SearchConfigurationError",
            error_message=str(exc),
        )
    except SearchServiceError as exc:
        logger.warning("Platform %s search service error", platform.name)
        return PlatformOutcome(
            platform_name=platform.name,
            success=False,
            error_type="SearchServiceError",
            error_message=str(exc),
        )
    except (KeyError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
        logger.error("Platform %s unexpected error: %s", platform.name, type(exc).__name__)
        return PlatformOutcome(
            platform_name=platform.name,
            success=False,
            error_type="UnexpectedError",
            error_message=type(exc).__name__,
        )


async def discover_raw_candidates(
    intent: QueryIntent,
    search_service: TavilySearchService | None = None,
    platforms: Sequence[PlatformSource] | None = None,
) -> list[RawCandidate]:
    """Execute concurrent discovery across all configured platforms and return deduplicated raw candidates.

    Args:
        intent: Validated query intent.
        search_service: Optional Tavily search service instance.
        platforms: Optional list of platform sources (defaults to all supported platforms).

    Returns:
        Deduplicated list of RawCandidate objects.

    Raises:
        HTTPException: When all platforms fail with mapped HTTP status codes (503, 429, 504, 502).
    """
    service = search_service or TavilySearchService()
    platform_list = list(platforms) if platforms is not None else get_all_platform_sources()

    if not platform_list:
        return []

    semaphore = asyncio.Semaphore(CONCURRENT_PLATFORM_SEARCH_LIMIT)
    tasks = [
        _execute_platform_search(platform, intent, service, semaphore)
        for platform in platform_list
    ]

    outcomes: list[PlatformOutcome] = await asyncio.gather(*tasks)

    successful_outcomes = [o for o in outcomes if o.success]
    failed_outcomes = [o for o in outcomes if not o.success]

    # Total platform failure
    if not successful_outcomes:
        error_types = [o.error_type for o in failed_outcomes]
        if any(t == "SearchConfigurationError" for t in error_types):
            logger.error("All platform searches failed due to search service configuration error")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Search provider service is not properly configured",
            )
        if any(t == "SearchRateLimitError" for t in error_types):
            logger.warning("All platform searches failed due to rate limits")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Search provider rate limit exceeded",
            )
        if any(t == "SearchTimeoutError" for t in error_types):
            logger.error("All platform searches timed out")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Search provider request timed out",
            )

        logger.error("All platform searches failed due to upstream search provider error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream search provider error",
        )

    # Collect and deduplicate candidates from successful platforms
    seen_urls: set[str] = set()
    deduped_candidates: list[RawCandidate] = []

    for outcome in successful_outcomes:
        for cand in outcome.candidates:
            if cand.canonical_url not in seen_urls:
                seen_urls.add(cand.canonical_url)
                deduped_candidates.append(cand)

    logger.info(
        "Platform discovery complete: %d platforms succeeded, %d failed; %d unique raw candidates discovered",
        len(successful_outcomes),
        len(failed_outcomes),
        len(deduped_candidates),
    )
    return deduped_candidates


async def discover_prospects(
    request: DiscoveryRequest,
    llm_service: BaseLLMService | None = None,
    search_service: TavilySearchService | None = None,
) -> DiscoveryResponse:
    """Orchestrate prospect discovery for a validated search request.

    Args:
        request: The validated user discovery query request.
        llm_service: Optional LLM provider instance; defaults to the configured singleton.
        search_service: Optional search service instance.

    Returns:
        DiscoveryResponse containing discovery status, query, and prospects list.

    Raises:
        HTTPException: With corresponding HTTP status code on upstream failures.
    """
    service = llm_service or get_llm_service()

    try:
        intent = await service.extract_query_intent(request.query)
    except LLMRateLimitError as exc:
        logger.warning("LLM rate limit encountered during query discovery")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM provider rate limit exceeded",
        ) from exc
    except LLMTimeoutError as exc:
        logger.error("LLM timeout encountered during query discovery")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM provider request timed out",
        ) from exc
    except LLMResponseParsingError as exc:
        logger.error("LLM response parsing failed during query discovery")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to parse LLM intent response",
        ) from exc
    except LLMConfigurationError as exc:
        logger.error("LLM service is not properly configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider service is not properly configured",
        ) from exc
    except LLMServiceError as exc:
        logger.error("Upstream LLM service error: %s", type(exc).__name__)
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

    raw_candidates = await discover_raw_candidates(intent, search_service=search_service)
    logger.info(
        "Phase 2 discovery retrieved %d raw candidate profiles; awaiting Phase 3 entity verification and resolution",
        len(raw_candidates),
    )

    # Phase 2 boundary: raw search candidates are NOT converted into verified Prospect entities yet.
    return DiscoveryResponse(
        success=True,
        query=request.query,
        total_prospects=0,
        prospects=[],
    )
