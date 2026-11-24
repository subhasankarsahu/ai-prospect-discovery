"""Unit tests for the Tavily search service with MockTransport."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings
from app.services.cache_service import DiskSearchCache
from app.services.search_service import (
    SearchConfigurationError,
    SearchRateLimitError,
    SearchServiceError,
    SearchTimeoutError,
    TavilySearchService,
)


@pytest.fixture
def test_settings() -> Settings:
    """Fixture returning settings configured for testing."""
    return Settings(
        tavily_api_key="tvly-test-key-12345",
        request_timeout_seconds=5,
        search_cache_enabled=False,
    )


@pytest.mark.asyncio
async def test_search_missing_api_key() -> None:
    """Verify SearchConfigurationError is raised before network requests when API key is missing."""
    settings = Settings(tavily_api_key="", search_cache_enabled=False)
    service = TavilySearchService(settings=settings)

    with pytest.raises(SearchConfigurationError, match="TAVILY_API_KEY is not configured"):
        await service.search("test query")


@pytest.mark.asyncio
async def test_search_successful_bearer_auth(test_settings: Settings) -> None:
    """Verify search sends Authorization Bearer header and parses results."""
    tavily_response_data = {
        "results": [
            {"url": "https://linkedin.com/in/testuser", "title": "Test User", "content": "AI Specialist"},
        ]
    }

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer tvly-test-key-12345"
        body = json.loads(request.read())
        assert body["query"] == "ai researchers"
        assert body["max_results"] == 5
        assert body["search_depth"] == "basic"
        return httpx.Response(200, json=tavily_response_data)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = TavilySearchService(settings=test_settings, client=client)
        results = await service.search("ai researchers", include_domains=["linkedin.com"])

        assert len(results) == 1
        assert results[0].url == "https://linkedin.com/in/testuser"
        assert results[0].title == "Test User"
        assert results[0].snippet == "AI Specialist"


@pytest.mark.asyncio
async def test_search_rate_limit_retry_success(test_settings: Settings) -> None:
    """Verify recovery on 429 when retry succeeds within 5s budget."""
    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"results": [{"url": "https://x.com/user", "title": "User", "content": "Bio"}]})

    transport = httpx.MockTransport(mock_handler)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        async with httpx.AsyncClient(transport=transport) as client:
            service = TavilySearchService(settings=test_settings, client=client)
            results = await service.search("query")
            assert len(results) == 1
            assert call_count == 2
            mock_sleep.assert_called_once_with(1.0)


@pytest.mark.asyncio
async def test_search_rate_limit_exceeds_budget_aborts(test_settings: Settings) -> None:
    """Verify immediate abort without sleeping when Retry-After exceeds 5s budget."""
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "10"})

    transport = httpx.MockTransport(mock_handler)
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        async with httpx.AsyncClient(transport=transport) as client:
            service = TavilySearchService(settings=test_settings, client=client)
            with pytest.raises(SearchRateLimitError, match="exceeds maximum allowed retry budget"):
                await service.search("query")
            mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_search_rate_limit_exhausted(test_settings: Settings) -> None:
    """Verify SearchRateLimitError is raised after max retries exhausted."""
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "1"})

    transport = httpx.MockTransport(mock_handler)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        async with httpx.AsyncClient(transport=transport) as client:
            service = TavilySearchService(settings=test_settings, client=client)
            with pytest.raises(SearchRateLimitError, match="rate limit exceeded after retries"):
                await service.search("query")


@pytest.mark.asyncio
async def test_search_5xx_retry_and_exhaustion(test_settings: Settings) -> None:
    """Verify 5xx server error retries up to budget and raises SearchServiceError."""
    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(502, text="Bad Gateway")

    transport = httpx.MockTransport(mock_handler)
    with patch("asyncio.sleep", new_callable=AsyncMock):
        async with httpx.AsyncClient(transport=transport) as client:
            service = TavilySearchService(settings=test_settings, client=client)
            with pytest.raises(SearchServiceError, match="Tavily server error: 502"):
                await service.search("query")
            assert call_count == 3  # Initial + 2 retries


@pytest.mark.asyncio
async def test_search_401_fast_fail(test_settings: Settings) -> None:
    """Verify HTTP 401 client error fails immediately without retry."""
    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"detail": "Unauthorized"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = TavilySearchService(settings=test_settings, client=client)
        with pytest.raises(SearchConfigurationError, match="Invalid or unauthorized Tavily API key"):
            await service.search("query")
        assert call_count == 1  # No retries


@pytest.mark.asyncio
async def test_search_400_fast_fail(test_settings: Settings) -> None:
    """Verify HTTP 400 client error fails immediately without retry."""
    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, json={"detail": "Bad Request"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = TavilySearchService(settings=test_settings, client=client)
        with pytest.raises(SearchServiceError, match="client error: HTTP 400"):
            await service.search("query")
        assert call_count == 1  # No retries


@pytest.mark.asyncio
async def test_search_timeout_raises_search_timeout_error(test_settings: Settings) -> None:
    """Verify request timeout raises SearchTimeoutError."""
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = TavilySearchService(settings=test_settings, client=client)
        with pytest.raises(SearchTimeoutError, match="request timed out"):
            await service.search("query")


@pytest.mark.asyncio
async def test_search_cache_hit_avoids_http(tmp_path: Path, test_settings: Settings) -> None:
    """Verify a cache hit returns results without making any HTTP request."""
    settings = Settings(
        tavily_api_key="tvly-test",
        search_cache_enabled=True,
        search_cache_dir=str(tmp_path),
    )
    cache = DiskSearchCache(settings=settings)

    http_calls = 0
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal http_calls
        http_calls += 1
        return httpx.Response(200, json={"results": [{"url": "https://x.com/test", "title": "T", "content": "C"}]})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = TavilySearchService(settings=settings, client=client, cache=cache)

        # 1st call -> Cache miss, HTTP call made
        results1 = await service.search("founders", include_domains=["x.com"])
        assert http_calls == 1
        assert len(results1) == 1

        # 2nd call -> Cache hit, 0 additional HTTP calls
        results2 = await service.search("founders", include_domains=["x.com"])
        assert http_calls == 1
        assert len(results2) == 1
        assert results2[0].url == "https://x.com/test"
