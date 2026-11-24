"""Unit tests for multi-platform concurrent discovery orchestration."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.platforms.facebook import FacebookPlatform
from app.platforms.instagram import InstagramPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.threads import ThreadsPlatform
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
        if include_domains and "linkedin" in include_domains[0]:
            return [TavilySearchResult(url="https://linkedin.com/in/successful-user", title="L", snippet="S")]
        # X platform raises rate limit
        raise SearchRateLimitError("Rate limited")

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform(), XPlatform()],
        include_google_discovery=False,
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


# ============================================================================
# Google Discovery-Only Source Tests
# ============================================================================


@pytest.mark.asyncio
async def test_google_discovery_does_not_send_include_domains(sample_intent: QueryIntent) -> None:
    """Verify that Google unrestricted discovery does not send include_domains."""
    mock_service = AsyncMock(spec=TavilySearchService)
    mock_service.search.return_value = []

    await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[],
        include_google_discovery=True,
    )

    assert mock_service.search.call_count == 1
    call_kwargs = mock_service.search.call_args.kwargs
    assert call_kwargs.get("include_domains") is None


@pytest.mark.asyncio
async def test_google_discovery_valid_linkedin_url_becomes_linkedin_candidate(
    sample_intent: QueryIntent,
) -> None:
    """Verify a valid LinkedIn profile found via Google discovery is classified as LinkedIn."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if include_domains is None:
            # Google discovery search
            return [
                TavilySearchResult(
                    url="https://linkedin.com/in/discovered-ai-researcher",
                    title="Discovered Researcher",
                    snippet="Pioneer in AI",
                )
            ]
        return []

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform()],
        include_google_discovery=True,
    )

    assert len(candidates) == 1
    assert candidates[0].source_platform == "LinkedIn"
    assert candidates[0].canonical_url == "https://linkedin.com/in/discovered-ai-researcher"


@pytest.mark.asyncio
async def test_google_discovery_multi_platform_classification(sample_intent: QueryIntent) -> None:
    """Verify valid profile URLs from all supported platforms are classified correctly."""
    mock_service = AsyncMock(spec=TavilySearchService)

    google_results = [
        TavilySearchResult(url="https://x.com/jack", title="Jack", snippet="X bio"),
        TavilySearchResult(url="https://youtube.com/@mkbhd", title="MKBHD", snippet="Tech review"),
        TavilySearchResult(url="https://instagram.com/zuck", title="Zuck", snippet="IG bio"),
        TavilySearchResult(url="https://threads.net/@zuck", title="Zuck Threads", snippet="Threads bio"),
        TavilySearchResult(
            url="https://facebook.com/profile.php?id=100012345&utm_source=tracker",
            title="FB User",
            snippet="FB profile",
        ),
    ]

    async def mock_search(query: str, include_domains=None):
        if include_domains is None:
            return google_results
        return []

    mock_service.search.side_effect = mock_search

    all_platforms = [
        LinkedInPlatform(),
        XPlatform(),
        YouTubePlatform(),
        InstagramPlatform(),
        ThreadsPlatform(),
        FacebookPlatform(),
    ]

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=all_platforms,
        include_google_discovery=True,
    )

    by_platform = {c.source_platform: c for c in candidates}
    assert "X" in by_platform
    assert by_platform["X"].canonical_url == "https://x.com/jack"
    assert "YouTube" in by_platform
    assert by_platform["YouTube"].canonical_url == "https://youtube.com/@mkbhd"
    assert "Instagram" in by_platform
    assert by_platform["Instagram"].canonical_url == "https://instagram.com/zuck"
    assert "Threads" in by_platform
    assert by_platform["Threads"].canonical_url == "https://threads.net/@zuck"
    assert "Facebook" in by_platform
    # Preserves id parameter, purges tracking parameter
    assert by_platform["Facebook"].canonical_url == "https://facebook.com/profile.php?id=100012345"


@pytest.mark.asyncio
async def test_google_discovery_discards_invalid_unrelated_and_lookalike_urls(
    sample_intent: QueryIntent,
) -> None:
    """Verify unrelated, lookalike, credentials, and non-profile URLs are discarded."""
    mock_service = AsyncMock(spec=TavilySearchService)

    invalid_results = [
        TavilySearchResult(url="https://medium.com/@someone", title="Article", snippet="Text"),
        TavilySearchResult(url="https://linkedin.com.attacker.com/in/fake", title="Phish", snippet="Text"),
        TavilySearchResult(url="https://linkedin.com/company/acme", title="Company", snippet="Text"),
        TavilySearchResult(url="https://x.com/explore", title="Explore", snippet="Text"),
        TavilySearchResult(url="https://facebook.com/photo.php?fbid=123", title="Photo", snippet="Text"),
        TavilySearchResult(url="https://evil:pass@youtube.com/@valid", title="Creds", snippet="Text"),
    ]

    async def mock_search(query: str, include_domains=None):
        if include_domains is None:
            return invalid_results
        return []

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[
            LinkedInPlatform(),
            XPlatform(),
            YouTubePlatform(),
            InstagramPlatform(),
            ThreadsPlatform(),
            FacebookPlatform(),
        ],
        include_google_discovery=True,
    )

    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_google_discovery_never_creates_google_source_platform(
    sample_intent: QueryIntent,
) -> None:
    """Verify that candidates discovered through Google never receive 'Google' as source_platform."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if include_domains is None:
            return [
                TavilySearchResult(url="https://linkedin.com/in/expert", title="Expert", snippet="Bio"),
                TavilySearchResult(url="https://x.com/expert", title="Expert", snippet="Bio"),
            ]
        return []

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform(), XPlatform()],
        include_google_discovery=True,
    )

    assert len(candidates) == 2
    assert all(c.source_platform != "Google" for c in candidates)
    platforms_found = {c.source_platform for c in candidates}
    assert platforms_found == {"LinkedIn", "X"}


@pytest.mark.asyncio
async def test_google_discovery_deduplicates_with_platform_search(
    sample_intent: QueryIntent,
) -> None:
    """Verify that a candidate discovered by both platform search and Google is deduplicated."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if include_domains is not None:
            # LinkedIn platform search returns canonical profile with ref parameter
            return [
                TavilySearchResult(
                    url="https://linkedin.com/in/satyanadella?ref=search",
                    title="Satya Nadella",
                    snippet="CEO",
                )
            ]
        # Google search returns same profile with www and trailing slash
        return [
            TavilySearchResult(
                url="https://www.linkedin.com/in/satyanadella/",
                title="Satya Nadella",
                snippet="Microsoft CEO",
            )
        ]

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform()],
        include_google_discovery=True,
    )

    assert len(candidates) == 1
    assert candidates[0].canonical_url == "https://linkedin.com/in/satyanadella"


@pytest.mark.asyncio
async def test_google_discovery_failure_does_not_break_successful_platform_discovery(
    sample_intent: QueryIntent,
) -> None:
    """Verify that when Google search fails, candidates from successful platforms are still returned."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if include_domains is not None:
            return [
                TavilySearchResult(url="https://linkedin.com/in/successful", title="User", snippet="Bio")
            ]
        # Google unrestricted search fails
        raise SearchRateLimitError("Google rate limit")

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform()],
        include_google_discovery=True,
    )

    assert len(candidates) == 1
    assert candidates[0].canonical_url == "https://linkedin.com/in/successful"
    assert candidates[0].source_platform == "LinkedIn"


@pytest.mark.asyncio
async def test_google_discovery_success_zero_valid_profiles_treated_as_successful_empty(
    sample_intent: QueryIntent,
) -> None:
    """Verify that Google search returning zero valid profile URLs is treated as a successful empty outcome."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        # Returns general web pages, not social profiles
        return [
            TavilySearchResult(url="https://nytimes.com/article", title="News", snippet="Article"),
        ]

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform()],
        include_google_discovery=True,
    )

    assert candidates == []


# ============================================================================
# Total-Failure Error Majority & Priority Logic Tests
# ============================================================================


@pytest.mark.asyncio
async def test_orchestrator_majority_rate_limit_429(sample_intent: QueryIntent) -> None:
    """Verify 429 is returned when rate limits form a strict majority (>50%) of failed outcomes."""
    mock_service = AsyncMock(spec=TavilySearchService)

    # 6 sources: 4 rate limits, 1 timeout, 1 service error (4/6 = 66.7% > 50%)
    errors = [
        SearchRateLimitError("RL1"),
        SearchRateLimitError("RL2"),
        SearchRateLimitError("RL3"),
        SearchRateLimitError("RL4"),
        SearchTimeoutError("TO"),
        SearchServiceError("SE"),
    ]
    call_idx = 0

    async def mock_search(query: str, include_domains=None):
        nonlocal call_idx
        err = errors[call_idx % len(errors)]
        call_idx += 1
        raise err

    mock_service.search.side_effect = mock_search

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[
                LinkedInPlatform(),
                XPlatform(),
                YouTubePlatform(),
                InstagramPlatform(),
                ThreadsPlatform(),
                FacebookPlatform(),
            ],
            include_google_discovery=False,
        )

    assert exc_info.value.status_code == 429
    assert "rate limit exceeded" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_majority_timeout_504(sample_intent: QueryIntent) -> None:
    """Verify 504 is returned when timeouts form a strict majority (>50%) of failed outcomes."""
    mock_service = AsyncMock(spec=TavilySearchService)

    # 6 sources: 1 rate limit, 4 timeouts, 1 service error (4/6 = 66.7% > 50%)
    errors = [
        SearchRateLimitError("RL"),
        SearchTimeoutError("TO1"),
        SearchTimeoutError("TO2"),
        SearchTimeoutError("TO3"),
        SearchTimeoutError("TO4"),
        SearchServiceError("SE"),
    ]
    call_idx = 0

    async def mock_search(query: str, include_domains=None):
        nonlocal call_idx
        err = errors[call_idx % len(errors)]
        call_idx += 1
        raise err

    mock_service.search.side_effect = mock_search

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[
                LinkedInPlatform(),
                XPlatform(),
                YouTubePlatform(),
                InstagramPlatform(),
                ThreadsPlatform(),
                FacebookPlatform(),
            ],
            include_google_discovery=False,
        )

    assert exc_info.value.status_code == 504
    assert "timed out" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_tie_rate_limit_and_timeout_falls_back_to_502(
    sample_intent: QueryIntent,
) -> None:
    """Verify 502 is returned on equal rate-limit / timeout tie (no strict majority)."""
    mock_service = AsyncMock(spec=TavilySearchService)

    # 6 sources: 3 rate limits, 3 timeouts (3/6 = 50% -> not a strict majority > 50%)
    errors = [
        SearchRateLimitError("RL1"),
        SearchRateLimitError("RL2"),
        SearchRateLimitError("RL3"),
        SearchTimeoutError("TO1"),
        SearchTimeoutError("TO2"),
        SearchTimeoutError("TO3"),
    ]
    call_idx = 0

    async def mock_search(query: str, include_domains=None):
        nonlocal call_idx
        err = errors[call_idx % len(errors)]
        call_idx += 1
        raise err

    mock_service.search.side_effect = mock_search

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[
                LinkedInPlatform(),
                XPlatform(),
                YouTubePlatform(),
                InstagramPlatform(),
                ThreadsPlatform(),
                FacebookPlatform(),
            ],
            include_google_discovery=False,
        )

    assert exc_info.value.status_code == 502
    assert "upstream search provider error" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_three_way_mixed_failure_without_majority_falls_back_to_502(
    sample_intent: QueryIntent,
) -> None:
    """Verify 502 is returned on three-way mixed distribution without strict majority."""
    mock_service = AsyncMock(spec=TavilySearchService)

    # 6 sources: 2 rate limits, 2 timeouts, 2 service errors (2/6 = 33.3%)
    errors = [
        SearchRateLimitError("RL1"),
        SearchRateLimitError("RL2"),
        SearchTimeoutError("TO1"),
        SearchTimeoutError("TO2"),
        SearchServiceError("SE1"),
        SearchServiceError("SE2"),
    ]
    call_idx = 0

    async def mock_search(query: str, include_domains=None):
        nonlocal call_idx
        err = errors[call_idx % len(errors)]
        call_idx += 1
        raise err

    mock_service.search.side_effect = mock_search

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[
                LinkedInPlatform(),
                XPlatform(),
                YouTubePlatform(),
                InstagramPlatform(),
                ThreadsPlatform(),
                FacebookPlatform(),
            ],
            include_google_discovery=False,
        )

    assert exc_info.value.status_code == 502
    assert "upstream search provider error" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_configuration_error_precedence_over_majority(
    sample_intent: QueryIntent,
) -> None:
    """Verify 503 takes precedence even when rate limits form the numerical majority."""
    mock_service = AsyncMock(spec=TavilySearchService)

    # 6 sources: 1 configuration error, 5 rate limits
    errors = [
        SearchConfigurationError("Invalid key"),
        SearchRateLimitError("RL1"),
        SearchRateLimitError("RL2"),
        SearchRateLimitError("RL3"),
        SearchRateLimitError("RL4"),
        SearchRateLimitError("RL5"),
    ]
    call_idx = 0

    async def mock_search(query: str, include_domains=None):
        nonlocal call_idx
        err = errors[call_idx % len(errors)]
        call_idx += 1
        raise err

    mock_service.search.side_effect = mock_search

    with pytest.raises(HTTPException) as exc_info:
        await discover_raw_candidates(
            intent=sample_intent,
            search_service=mock_service,
            platforms=[
                LinkedInPlatform(),
                XPlatform(),
                YouTubePlatform(),
                InstagramPlatform(),
                ThreadsPlatform(),
                FacebookPlatform(),
            ],
            include_google_discovery=False,
        )

    assert exc_info.value.status_code == 503
    assert "not properly configured" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_orchestrator_partial_success_with_mixed_failures_returns_200(
    sample_intent: QueryIntent,
) -> None:
    """Verify partial success with mixed failures returns candidates without error."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if include_domains and "linkedin.com" in include_domains:
            return [TavilySearchResult(url="https://linkedin.com/in/success-user", title="User", snippet="Bio")]
        if include_domains and "x.com" in include_domains:
            raise SearchRateLimitError("Rate limited")
        if include_domains and "youtube.com" in include_domains:
            raise SearchTimeoutError("Timed out")
        raise SearchServiceError("Service error")

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform(), XPlatform(), YouTubePlatform()],
        include_google_discovery=False,
    )

    assert len(candidates) == 1
    assert candidates[0].source_platform == "LinkedIn"


@pytest.mark.asyncio
async def test_orchestrator_successful_empty_outcome_not_counted_in_failure_denominator(
    sample_intent: QueryIntent,
) -> None:
    """Verify that a successful search returning zero valid profiles prevents total failure."""
    mock_service = AsyncMock(spec=TavilySearchService)

    async def mock_search(query: str, include_domains=None):
        if include_domains and "linkedin.com" in include_domains:
            # Healthy search, but returns non-profile page (0 profile candidates)
            return [TavilySearchResult(url="https://linkedin.com/company/acme", title="Company", snippet="About")]
        # Other platforms fail with rate limits
        raise SearchRateLimitError("Rate limited")

    mock_service.search.side_effect = mock_search

    candidates = await discover_raw_candidates(
        intent=sample_intent,
        search_service=mock_service,
        platforms=[LinkedInPlatform(), XPlatform(), YouTubePlatform()],
        include_google_discovery=False,
    )

    assert candidates == []
