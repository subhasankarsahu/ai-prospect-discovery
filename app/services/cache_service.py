"""Disk-based search caching with atomic replacement, TTL expiration, and fail-open resilience."""

import hashlib
import json
import logging
import os
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from app.config import Settings, get_settings
from app.schemas_internal import TavilySearchResult

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 86400  # 24 hours


class DiskSearchCache:
    """Local filesystem cache for external search responses."""

    def __init__(
        self,
        settings: Settings | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Initialize the disk search cache.

        Args:
            settings: Application settings containing cache enablement and directory.
            ttl_seconds: Time-to-live in seconds for cached entries.
        """
        self.settings = settings or get_settings()
        self.cache_dir = Path(self.settings.search_cache_dir)
        self.ttl_seconds = ttl_seconds
        self.enabled = self.settings.search_cache_enabled

        if self.enabled:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("Failed to initialize cache directory: %s", type(exc).__name__)
                self.enabled = False

    def _generate_cache_key(self, query: str, domains: Sequence[str] | None = None) -> str:
        """Generate a SHA-256 cache key from normalized query and sorted domain list.

        Args:
            query: User search query string.
            domains: Optional list of domains targeted by search.

        Returns:
            Hex-encoded SHA-256 digest string.
        """
        normalized_query = query.strip().lower()
        normalized_domains = sorted({d.strip().lower() for d in (domains or [])})
        compound_key = f"{normalized_query}::{','.join(normalized_domains)}"
        return hashlib.sha256(compound_key.encode("utf-8")).hexdigest()

    def get(
        self,
        query: str,
        domains: Sequence[str] | None = None,
    ) -> list[TavilySearchResult] | None:
        """Retrieve cached search results if present, uncorrupted, and not expired.

        Args:
            query: User search query.
            domains: Target domain filters.

        Returns:
            List of TavilySearchResult objects on cache hit; None on miss, expiry, or failure.
        """
        if not self.enabled:
            return None

        cache_key = self._generate_cache_key(query, domains)
        target_path = self.cache_dir / f"{cache_key}.json"

        if not target_path.exists():
            return None

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            cached_at = payload.get("cached_at", 0)
            if time.time() - cached_at > self.ttl_seconds:
                logger.debug("Cache entry expired for key %s", cache_key[:12])
                try:
                    target_path.unlink(missing_ok=True)
                except OSError:
                    pass
                return None

            items = payload.get("data", [])
            logger.debug("Cache hit for key %s", cache_key[:12])
            return [TavilySearchResult.model_validate(item) for item in items]

        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            logger.warning("Corrupted or unreadable cache for key %s: %s", cache_key[:12], type(exc).__name__)
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def set(
        self,
        query: str,
        results: list[TavilySearchResult],
        domains: Sequence[str] | None = None,
    ) -> None:
        """Atomically persist search results to disk using a unique temporary file.

        Args:
            query: User search query.
            results: List of search results to cache.
            domains: Target domain filters.
        """
        if not self.enabled:
            return

        cache_key = self._generate_cache_key(query, domains)
        target_path = self.cache_dir / f"{cache_key}.json"
        temp_path = self.cache_dir / f".tmp_{cache_key}_{uuid.uuid4().hex}.tmp"

        payload = {
            "cached_at": time.time(),
            "ttl_seconds": self.ttl_seconds,
            "data": [r.model_dump() for r in results],
        }

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(temp_path, target_path)
            logger.debug("Cached %d results for key %s", len(results), cache_key[:12])
        except OSError as exc:
            logger.warning("Failed to write search cache for key %s: %s", cache_key[:12], type(exc).__name__)
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
