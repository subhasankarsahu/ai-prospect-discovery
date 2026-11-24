"""Unit tests for the resilient disk search cache service."""

import logging
import time
from pathlib import Path

import pytest

from app.config import Settings
from app.schemas_internal import TavilySearchResult
from app.services.cache_service import DiskSearchCache


def test_cache_miss_and_hit(tmp_path: Path) -> None:
    """Verify cache miss returns None, set saves data, and subsequent get returns data."""
    settings = Settings(search_cache_enabled=True, search_cache_dir=str(tmp_path))
    cache = DiskSearchCache(settings=settings, ttl_seconds=3600)

    results = [
        TavilySearchResult(url="https://linkedin.com/in/johndoe", title="John Doe", snippet="Engineer"),
    ]

    # Miss
    assert cache.get("ai founders", ["linkedin.com"]) is None

    # Set
    cache.set("ai founders", results, ["linkedin.com"])

    # Hit
    cached = cache.get("ai founders", ["linkedin.com"])
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].url == "https://linkedin.com/in/johndoe"
    assert cached[0].title == "John Doe"


def test_cache_expiration(tmp_path: Path) -> None:
    """Verify entries past TTL expire and are removed."""
    settings = Settings(search_cache_enabled=True, search_cache_dir=str(tmp_path))
    cache = DiskSearchCache(settings=settings, ttl_seconds=1)

    results = [TavilySearchResult(url="https://x.com/user", title="User", snippet="Bio")]
    cache.set("founders", results, ["x.com"])

    assert cache.get("founders", ["x.com"]) is not None

    # Wait for TTL expiry
    time.sleep(1.1)
    assert cache.get("founders", ["x.com"]) is None


def test_cache_corruption_recovery(tmp_path: Path) -> None:
    """Verify corrupted JSON files are deleted and handled as a cache miss."""
    settings = Settings(search_cache_enabled=True, search_cache_dir=str(tmp_path))
    cache = DiskSearchCache(settings=settings, ttl_seconds=3600)

    # Pre-write invalid JSON file
    cache_key = cache._generate_cache_key("founders", ["x.com"])
    corrupt_file = tmp_path / f"{cache_key}.json"
    corrupt_file.write_text("invalid json content {{{", encoding="utf-8")

    assert corrupt_file.exists()
    assert cache.get("founders", ["x.com"]) is None
    # File should be cleaned up
    assert not corrupt_file.exists()


def test_cache_atomic_concurrent_writes(tmp_path: Path) -> None:
    """Verify multiple writes to the same key complete cleanly without corruption."""
    settings = Settings(search_cache_enabled=True, search_cache_dir=str(tmp_path))
    cache = DiskSearchCache(settings=settings, ttl_seconds=3600)

    results1 = [TavilySearchResult(url="https://x.com/u1", title="U1", snippet="Bio1")]
    results2 = [TavilySearchResult(url="https://x.com/u2", title="U2", snippet="Bio2")]

    cache.set("query", results1, ["x.com"])
    cache.set("query", results2, ["x.com"])

    cached = cache.get("query", ["x.com"])
    assert cached is not None
    assert cached[0].url in ("https://x.com/u1", "https://x.com/u2")


def test_cache_disabled(tmp_path: Path) -> None:
    """Verify get returns None and set does not write when cache is disabled."""
    settings = Settings(search_cache_enabled=False, search_cache_dir=str(tmp_path))
    cache = DiskSearchCache(settings=settings, ttl_seconds=3600)

    results = [TavilySearchResult(url="https://x.com/u1", title="U1", snippet="Bio1")]
    cache.set("query", results, ["x.com"])

    assert cache.get("query", ["x.com"]) is None
    assert list(tmp_path.glob("*.json")) == []


def test_cache_logging_privacy(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Verify sensitive search queries and snippets never appear in cache logs."""
    settings = Settings(search_cache_enabled=True, search_cache_dir=str(tmp_path))
    cache = DiskSearchCache(settings=settings, ttl_seconds=3600)

    with caplog.at_level(logging.DEBUG):
        cache.set("super secret query about alice", [
            TavilySearchResult(url="https://x.com/alice", title="Alice Title", snippet="Secret Bio")
        ])
        cache.get("super secret query about alice")

    for record in caplog.records:
        assert "super secret query" not in record.message
        assert "Secret Bio" not in record.message
