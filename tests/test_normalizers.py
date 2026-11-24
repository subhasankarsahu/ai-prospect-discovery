"""Unit tests for URL, name, and profile handle normalization."""

import pytest

from app.utils.normalizers import canonical_url, extract_handle, normalize_name


@pytest.mark.parametrize(
    "raw_url, expected",
    [
        (
            "http://www.linkedin.com/in/john-doe/?ref=search",
            "https://linkedin.com/in/john-doe",
        ),
        (
            "https://twitter.com/sama?s=20&t=xyz#frag",
            "https://x.com/sama",
        ),
        (
            "https://www.youtube.com/@veritasium/?feature=share",
            "https://youtube.com/@veritasium",
        ),
        (
            "https://www.facebook.com/profile.php?id=100012345&utm_source=feed",
            "https://facebook.com/profile.php?id=100012345",
        ),
        (
            "https://facebook.com/zuck?fbclid=123",
            "https://facebook.com/zuck",
        ),
    ],
)
def test_canonical_url(raw_url: str, expected: str) -> None:
    """Verify URL canonicalization cleans query parameters, fragments, www, and forces https."""
    assert canonical_url(raw_url) == expected


@pytest.mark.parametrize(
    "raw_name, expected",
    [
        ("John   Doe", "john doe"),
        ("  Alice   M.   Smith  ", "alice m. smith"),
        ("Dr. René  Müller", "dr. rené müller"),
        ("Mary-Jane O'Connor", "mary-jane o'connor"),
        ("Ｊｏｈｎ Ｄｏｅ", "john doe"),  # Full-width NFKC normalization
    ],
)
def test_normalize_name(raw_name: str, expected: str) -> None:
    """Verify name normalization performs Unicode NFKC, collapses whitespace, and lowercases."""
    assert normalize_name(raw_name) == expected


@pytest.mark.parametrize(
    "url, platform, expected_handle",
    [
        ("https://linkedin.com/in/john-doe", "LinkedIn", "john-doe"),
        ("https://www.linkedin.com/in/jane_doe-123/", "linkedin", "jane_doe-123"),
        ("https://x.com/sama", "X", "sama"),
        ("https://twitter.com/jack", "Twitter", "jack"),
        ("https://youtube.com/@mkbhd", "YouTube", "mkbhd"),
        ("https://youtube.com/channel/UC123456789", "YouTube", "uc123456789"),
        ("https://youtube.com/c/CreatorName", "YouTube", "creatorname"),
        ("https://instagram.com/zuck", "Instagram", "zuck"),
        ("https://threads.net/@zuck", "Threads", "zuck"),
        ("https://threads.net/zuck", "Threads", "zuck"),
        ("https://facebook.com/profile.php?id=100012345", "Facebook", "id:100012345"),
        ("https://facebook.com/zuck", "Facebook", "zuck"),
    ],
)
def test_extract_handle_valid(url: str, platform: str, expected_handle: str) -> None:
    """Verify handle extraction across all six supported platforms."""
    assert extract_handle(url, platform) == expected_handle


@pytest.mark.parametrize(
    "url, platform",
    [
        ("https://linkedin.com/company/google", "LinkedIn"),
        ("https://linkedin.com/feed", "LinkedIn"),
        ("https://x.com/explore", "X"),
        ("https://x.com/home", "X"),
        ("https://youtube.com/watch?v=123", "YouTube"),
        ("https://youtube.com/shorts/123", "YouTube"),
        ("https://instagram.com/p/12345", "Instagram"),
        ("https://instagram.com/explore", "Instagram"),
        ("https://threads.net/@user/post/123", "Threads"),
        ("https://facebook.com/photo.php?fbid=123", "Facebook"),
        ("http://x.com/user", "X"),  # HTTP rejected
        ("https://evil.com/in/john", "LinkedIn"),  # Untrusted domain
    ],
)
def test_extract_handle_invalid_and_reserved_paths(url: str, platform: str) -> None:
    """Verify that reserved paths, media URLs, and untrusted hosts return None."""
    assert extract_handle(url, platform) is None
