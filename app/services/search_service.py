"""Tavily search API integration service with Bearer auth, retries, and disk caching."""

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.schemas_internal import TavilySearchResult
from app.services.cache_service import DiskSearchCache

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"
MAX_RETRY_SLEEP_BUDGET_SECONDS = 5.0
MAX_RETRIES = 2


class SearchServiceError(Exception):
    """Base exception for search service failures."""


class SearchConfigurationError(SearchServiceError):
    """Raised when search service is misconfigured or API key is missing/invalid."""


class SearchTimeoutError(SearchServiceError):
    """Raised when external search request times out."""


class SearchRateLimitError(SearchServiceError):
    """Raised when rate limit (429) persists or retry wait exceeds budget."""


class TavilySearchService:
    """Async Tavily Search client providing resilient search with caching and retry budgets."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        cache: DiskSearchCache | None = None,
    ) -> None:
        """Initialize the Tavily search service.

        Args:
            settings: Application settings containing tavily_api_key and timeout.
            client: Optional reusable HTTPX client (useful for connection pooling or testing).
            cache: Optional DiskSearchCache instance for caching search responses.
        """
        self.settings = settings or get_settings()
        self._external_client = client
        self.cache = cache or DiskSearchCache(settings=self.settings)

    async def _execute_with_retry(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        """Execute HTTP request with strict retry budget and exponential backoff.

        Args:
            client: Active HTTPX client.
            payload: JSON request body.
            headers: HTTP request headers including Bearer token.

        Returns:
            Successful httpx.Response.

        Raises:
            SearchTimeoutError: When request exceeds timeout.
            SearchRateLimitError: When rate-limited and retries/budget exhausted.
            SearchConfigurationError: On permanent authentication failure (401).
            SearchServiceError: On other HTTP client/server errors or network failures.
        """
        attempt = 0
        total_sleep_time = 0.0
        backoff_seconds = 1.0

        while True:
            try:
                response = await client.post(
                    TAVILY_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=float(self.settings.request_timeout_seconds),
                )

                if response.status_code == 200:
                    return response

                # Rate Limit (429)
                if response.status_code == 429:
                    attempt += 1
                    if attempt > MAX_RETRIES:
                        logger.warning("Tavily rate limit exceeded after %d retries", MAX_RETRIES)
                        raise SearchRateLimitError("Tavily search rate limit exceeded after retries")

                    retry_after_str = response.headers.get("Retry-After")
                    sleep_time = backoff_seconds
                    if retry_after_str:
                        try:
                            sleep_time = float(retry_after_str)
                        except ValueError:
                            sleep_time = backoff_seconds

                    if total_sleep_time + sleep_time > MAX_RETRY_SLEEP_BUDGET_SECONDS:
                        logger.warning(
                            "Tavily rate limit retry sleep (%.2fs) exceeds 5s budget; aborting",
                            total_sleep_time + sleep_time,
                        )
                        raise SearchRateLimitError(
                            "Tavily rate limit wait exceeds maximum allowed retry budget (5.0s)"
                        )

                    logger.info("Tavily 429 rate limit hit; retrying attempt %d in %.2fs", attempt, sleep_time)
                    total_sleep_time += sleep_time
                    await asyncio.sleep(sleep_time)
                    backoff_seconds *= 2.0
                    continue

                # Server Errors (5xx)
                if response.status_code >= 500:
                    attempt += 1
                    if attempt > MAX_RETRIES:
                        logger.error("Tavily server error %d after retries", response.status_code)
                        raise SearchServiceError(f"Tavily server error: {response.status_code}")

                    if total_sleep_time + backoff_seconds > MAX_RETRY_SLEEP_BUDGET_SECONDS:
                        logger.warning("Tavily retry sleep exceeds 5s budget on 5xx; aborting")
                        raise SearchServiceError(f"Tavily server error: {response.status_code}")

                    logger.info("Tavily 5xx error %d; retrying attempt %d in %.2fs", response.status_code, attempt, backoff_seconds)
                    total_sleep_time += backoff_seconds
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2.0
                    continue

                # Client Errors (4xx non-429: fast fail, zero retries)
                if response.status_code == 401:
                    logger.error("Tavily authentication failed (HTTP 401)")
                    raise SearchConfigurationError("Invalid or unauthorized Tavily API key")

                logger.error("Tavily client error: HTTP %d", response.status_code)
                raise SearchServiceError(f"Tavily API client error: HTTP {response.status_code}")

            except httpx.TimeoutException as exc:
                logger.error("Tavily API request timed out after %ds", self.settings.request_timeout_seconds)
                raise SearchTimeoutError("Tavily search request timed out") from exc
            except (SearchServiceError, SearchConfigurationError, SearchTimeoutError, SearchRateLimitError):
                raise
            except httpx.RequestError as exc:
                attempt += 1
                if attempt > MAX_RETRIES or (total_sleep_time + backoff_seconds > MAX_RETRY_SLEEP_BUDGET_SECONDS):
                    logger.error("Tavily network error after retries: %s", type(exc).__name__)
                    raise SearchServiceError(f"Tavily network error: {type(exc).__name__}") from exc

                logger.info("Transient Tavily network error (%s); retrying in %.2fs", type(exc).__name__, backoff_seconds)
                total_sleep_time += backoff_seconds
                await asyncio.sleep(backoff_seconds)
                backoff_seconds *= 2.0

    async def search(
        self,
        query: str,
        include_domains: Sequence[str] | None = None,
    ) -> list[TavilySearchResult]:
        """Perform search through Tavily with caching, Bearer authentication, and retry limits.

        Args:
            query: User's search query string.
            include_domains: Optional list of domains to restrict search to.

        Returns:
            List of TavilySearchResult objects.

        Raises:
            SearchConfigurationError: If TAVILY_API_KEY is missing or invalid.
            SearchTimeoutError: If request times out.
            SearchRateLimitError: If rate limits persist.
            SearchServiceError: On other search API failures.
        """
        api_key = self.settings.tavily_api_key.strip()
        if not api_key:
            raise SearchConfigurationError("TAVILY_API_KEY is not configured in settings")

        domains_list = list(include_domains) if include_domains else []

        # Check local cache first
        if self.cache:
            cached_results = self.cache.get(query, domains_list)
            if cached_results is not None:
                return cached_results

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_domains": domains_list,
        }

        if self._external_client is not None:
            response = await self._execute_with_retry(self._external_client, payload, headers)
            raw_results = response.json().get("results", [])
        else:
            async with httpx.AsyncClient() as client:
                response = await self._execute_with_retry(client, payload, headers)
                raw_results = response.json().get("results", [])

        results = [
            TavilySearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("content", ""),
            )
            for r in raw_results
            if r.get("url")
        ]

        if self.cache:
            self.cache.set(query, results, domains_list)

        return results
