"""Discovery service orchestrator for candidate prospect retrieval."""

import asyncio
import logging
from collections.abc import Sequence

from fastapi import HTTPException, status

from app.platforms import get_all_platform_sources
from app.platforms.base import PlatformSource
from app.schemas import DiscoveryRequest, DiscoveryResponse, QueryIntent
from app.schemas_internal import PlatformOutcome, RawCandidate
from app.services.deduplication_service import deduplicate_candidates
from app.services.llm_service import (
    BaseLLMService,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMServiceError,
    LLMTimeoutError,
    get_llm_service,
)
from app.services.profile_extractor import enrich_candidate_contacts
from app.services.prospect_service import assemble_discovery_response
from app.services.relevance_service import classify_and_verify_candidates
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


def _build_google_discovery_query(intent: QueryIntent) -> str:
    """Build dynamic query for unrestricted Google discovery search from intent fields."""
    terms: list[str] = [f'"{intent.interest.strip()}"']

    if intent.target_type and intent.target_type.lower() not in ("individual", "other", "any", ""):
        terms.append(intent.target_type.strip())

    if intent.audience and intent.audience.strip():
        terms.append(intent.audience.strip())

    if intent.location:
        loc_parts = [
            part.strip()
            for part in (intent.location.city, intent.location.state, intent.location.country)
            if part and part.strip()
        ]
        if loc_parts:
            terms.append(" ".join(loc_parts))

    return " ".join(terms)


async def _execute_google_discovery(
    intent: QueryIntent,
    classifiers: Sequence[PlatformSource],
    search_service: TavilySearchService,
    semaphore: asyncio.Semaphore,
) -> PlatformOutcome:
    """Execute unrestricted discovery search and classify candidate URLs across supported platforms."""
    try:
        query = _build_google_discovery_query(intent)
        async with semaphore:
            results = await search_service.search(
                query=query,
                include_domains=None,
            )

        candidates: list[RawCandidate] = []
        for r in results:
            for platform in classifiers:
                if platform.is_profile_url(r.url):
                    candidates.append(
                        RawCandidate(
                            source_platform=platform.name,
                            canonical_url=platform.extract_canonical_url(r.url),
                            title=r.title,
                            snippet=r.snippet,
                            search_query=query,
                        )
                    )
                    break

        return PlatformOutcome(
            platform_name="Google",
            success=True,
            candidates=candidates,
        )
    except asyncio.CancelledError:
        raise
    except SearchRateLimitError as exc:
        logger.warning("Google discovery rate limit exceeded")
        return PlatformOutcome(
            platform_name="Google",
            success=False,
            error_type="SearchRateLimitError",
            error_message=str(exc),
        )
    except SearchTimeoutError as exc:
        logger.warning("Google discovery request timed out")
        return PlatformOutcome(
            platform_name="Google",
            success=False,
            error_type="SearchTimeoutError",
            error_message=str(exc),
        )
    except SearchConfigurationError as exc:
        logger.error("Google discovery configuration error")
        return PlatformOutcome(
            platform_name="Google",
            success=False,
            error_type="SearchConfigurationError",
            error_message=str(exc),
        )
    except SearchServiceError as exc:
        logger.warning("Google discovery search service error")
        return PlatformOutcome(
            platform_name="Google",
            success=False,
            error_type="SearchServiceError",
            error_message=str(exc),
        )
    except (KeyError, ValueError, TypeError, AttributeError, RuntimeError) as exc:
        logger.error("Google discovery unexpected error: %s", type(exc).__name__)
        return PlatformOutcome(
            platform_name="Google",
            success=False,
            error_type="UnexpectedError",
            error_message=type(exc).__name__,
        )


async def discover_raw_candidates(
    intent: QueryIntent,
    search_service: TavilySearchService | None = None,
    platforms: Sequence[PlatformSource] | None = None,
    include_google_discovery: bool = True,
) -> list[RawCandidate]:
    """Execute concurrent discovery across all configured platforms and return deduplicated raw candidates.

    Args:
        intent: Validated query intent.
        search_service: Optional Tavily search service instance.
        platforms: Optional list of platform sources (defaults to all supported platforms).
        include_google_discovery: Whether to include unrestricted Google discovery search.

    Returns:
        Deduplicated list of RawCandidate objects.

    Raises:
        HTTPException: When all platforms fail with mapped HTTP status codes (503, 429, 504, 502).
    """
    service = search_service or TavilySearchService()
    platform_list = list(platforms) if platforms is not None else get_all_platform_sources()

    if not platform_list and not include_google_discovery:
        return []

    semaphore = asyncio.Semaphore(CONCURRENT_PLATFORM_SEARCH_LIMIT)
    tasks = [
        _execute_platform_search(platform, intent, service, semaphore)
        for platform in platform_list
    ]

    if include_google_discovery:
        classifiers = platform_list if platforms is not None else get_all_platform_sources()
        tasks.append(_execute_google_discovery(intent, classifiers, service, semaphore))

    outcomes: list[PlatformOutcome] = await asyncio.gather(*tasks)

    successful_outcomes = [o for o in outcomes if o.success]
    failed_outcomes = [o for o in outcomes if not o.success]

    # Total failure: all sources failed
    if not successful_outcomes:
        total_failures = len(failed_outcomes)
        if total_failures == 0:
            return []

        error_types = [o.error_type for o in failed_outcomes]

        # 1. Any SearchConfigurationError takes precedence -> 503
        if any(t == "SearchConfigurationError" for t in error_types):
            logger.error("All discovery searches failed due to search service configuration error")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Search provider service is not properly configured",
            )

        # 2. Strict majority rule (>50% of failed outcomes)
        rate_limit_count = sum(1 for t in error_types if t == "SearchRateLimitError")
        timeout_count = sum(1 for t in error_types if t == "SearchTimeoutError")
        majority_threshold = total_failures / 2.0

        if rate_limit_count > majority_threshold:
            logger.warning(
                "All discovery searches failed; rate limit dominant (%d/%d)",
                rate_limit_count,
                total_failures,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Search provider rate limit exceeded",
            )

        if timeout_count > majority_threshold:
            logger.error(
                "All discovery searches timed out; timeout dominant (%d/%d)",
                timeout_count,
                total_failures,
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Search provider request timed out",
            )

        # 3. Otherwise: ties, mixed failures, or generic errors without strict majority -> 502
        logger.error(
            "All discovery searches failed without a clear rate-limit or timeout majority (%d failures: %d rate limits, %d timeouts)",
            total_failures,
            rate_limit_count,
            timeout_count,
        )
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
        "Platform discovery retrieved %d raw candidate profiles for query %r",
        len(raw_candidates),
        request.query,
    )

    if not raw_candidates:
        return DiscoveryResponse(
            success=True,
            query=request.query,
            total_prospects=0,
            prospects=[],
        )

    try:
        verified_candidates = await classify_and_verify_candidates(
            intent=intent,
            candidates=raw_candidates,
            llm_service=service,
        )
    except LLMRateLimitError as exc:
        logger.warning("LLM rate limit encountered during candidate classification")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM provider rate limit exceeded",
        ) from exc
    except LLMTimeoutError as exc:
        logger.error("LLM timeout encountered during candidate classification")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM provider request timed out",
        ) from exc
    except LLMResponseParsingError as exc:
        logger.error("LLM response parsing failed during candidate classification")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to parse LLM candidate classification response",
        ) from exc
    except LLMConfigurationError as exc:
        logger.error("LLM service is not properly configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider service is not properly configured",
        ) from exc
    except LLMServiceError as exc:
        logger.error("Upstream LLM service error during classification: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream LLM provider error",
        ) from exc

    if not verified_candidates:
        logger.info("No candidates passed verification for query %r", request.query)
        return DiscoveryResponse(
            success=True,
            query=request.query,
            total_prospects=0,
            prospects=[],
        )

    enriched_candidates = enrich_candidate_contacts(verified_candidates)
    prospect_groups = deduplicate_candidates(enriched_candidates)

    return assemble_discovery_response(
        query=request.query,
        prospect_groups=prospect_groups,
    )
