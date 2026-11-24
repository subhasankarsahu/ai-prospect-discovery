"""Unit tests for multi-platform concurrent discovery orchestration."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.platforms.linkedin import LinkedInPlatform
from app.platforms.x import XPlatform
from app.platforms.youtube import YouTubePlatform
from app.schemas import QueryIntent
from app.schemas_internal import TavilySearchResult
from app.services.discovery_service import discover_raw_candidates
from app.services.search_service import (
    SearchConfigurationError,
    SearchRateLimitError,
    SearchServiceError,
    SearchTimeoutError,
    TavilySearchService,
)


@pytest.fixture
def sample_intent() -> QueryIntent:
    """Fixture returning sample query intent."""
    return QueryIntent(
        is_prospect_query=True,
        interest="Artificial Intelligence",
        target_type="founder",
    )


@pytest.mark.asyncio
async def test_orchestrator_concurrency_limit(sample_intent: QueryIntent) -> None:
    """Verify that concurrent platform searches are bounded by semaphore limit of 3."""
    in_flight = 0
    max_in_flight = 0

    async def mock_search(query: str, include_domains=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return [TavilySearchResult(url="https://linkedin.com/in/test", title="T", snippet="S")]

    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.side_effect = mock_search

    # Test with 6 platforms
    platforms = [
        LinkedInPlatform(),
        XPlatform(),
        YouTubePlatform(),
        LinkedInPlatform(),
        XPlatform(),
        YouTubePlatform(),
    ]

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=platforms,
    )
    assert max_in_flight <= 3
    assert len(candidates) >= 1


@pytest.mark.asyncio
async def test_orchestrator_cancellation_propagation(sample_intent: QueryIntent) -> None:
    """Verify that asyncio.CancelledError is not swallowed and propagates properly."""
    async def mock_hanging_search(query: str, include_domains=None):
        await asyncio.sleep(10)
        return []

    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.side_effect = mock_hanging_search

    task = asyncio.create_task(
        discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[LinkedInPlatform()],
        )
    )
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_orchestrator_partial_platform_failure(sample_intent: QueryIntent) -> None:
    """Verify partial platform failure returns candidates from successful platforms."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if "linkedin" in include_domains[0]:
            return [TavilySearchResult(url="https://linkedin.com/in/successful-user", title="L", snippet="S")]
        # X platform raises rate limit
        raise SearchRateLimitError("Rate limited")

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform(), XPlatform()],
    )

    assert len(candidates) == 1
    assert candidates[0].source_platform == "LinkedIn"
    assert candidates[0].canonical_url == "https://linkedin.com/in/successful-user"


@pytest.mark.asyncio
async def test_orchestrator_total_failure_429(sample_intent: QueryIntent) -> None:
    """Verify total platform failure due to rate limits raises HTTPException 429."""
    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.side_effect = SearchRateLimitError("Rate limited")

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[LinkedInPlatform(), XPlatform()],
        )
    assert exc_info.value.status_code == 429
    assert "rate limit exceeded" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_total_failure_504(sample_intent: QueryIntent) -> None:
    """Verify total platform failure due to timeouts raises HTTPException 504."""
    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.side_effect = SearchTimeoutError("Timed out")

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[LinkedInPlatform(), XPlatform()],
        )
    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_total_failure_503(sample_intent: QueryIntent) -> None:
    """Verify total platform failure due to configuration raises HTTPException 503."""
    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.side_effect = SearchConfigurationError("Missing key")

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[LinkedInPlatform(), XPlatform()],
        )
    assert exc_info.value.status_code == 503
    assert "not properly configured" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_total_failure_502(sample_intent: QueryIntent) -> None:
    """Verify total platform failure due to upstream 5xx raises HTTPException 502."""
    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.side_effect = SearchServiceError("502 Server Error")

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[LinkedInPlatform(), XPlatform()],
        )
    assert exc_info.value.status_code == 502
    assert "upstream search provider error" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_successful_empty_discovery(sample_intent: QueryIntent) -> None:
    """Verify healthy search producing zero valid profile URLs returns empty list without error."""
    mock_service = AsyncMock(spec=TavilySearchService)
    # Search succeeds, but returns only company or search pages (not personal profile URLs)
    mock_service.search.return_value = [
        TavilySearchResult(url="https://linkedin.com/company/some-corp", title="Corp", snippet="About"),
        TavilySearchResult(url="https://x.com/explore", title="Explore", snippet="Trending"),
    ]

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform(), XPlatform()],
    )
    assert candidates == []


@pytest.mark.asyncio
async def test_orchestrator_candidate_deduplication(sample_intent: QueryIntent) -> None:
    """Verify candidate profiles yielding identical canonical URLs are deduplicated."""
    mock_service = AsyncMock(spec=TavilySearchService)
    # Multiple search results pointing to the same canonical profile
    mock_service.search.return_value = [
        TavilySearchResult(url="https://x.com/sama?ref=search", title="Sam Altman", snippet="CEO"),
        TavilySearchResult(url="https://twitter.com/sama/", title="Sam Altman", snippet="OpenAI"),
    ]

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[XPlatform()],
    )
    # Both normalize to https://x.com/sama or https://twitter.com/sama -> exactly 1 unique canonical URL
    assert len(candidates) == 1
    assert candidates[0].canonical_url in ("https://x.com/sama", "https://twitter.com/sama")
