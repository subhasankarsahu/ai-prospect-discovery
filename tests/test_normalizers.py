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
            "https://m.facebook.com/profile.php?id=100012345&fbclid=abc&ref=bookmarks",
            "https://facebook.com/profile.php?id=100012345",
        ),
        (
            "https://facebook.com/Profile.php?ID=100012345&utm_medium=cpc",
            "https://facebook.com/profile.php?id=100012345",
        ),
        (
            "https://facebook.com/profile.php?id=67890&utm_campaign=spring",
            "https://facebook.com/profile.php?id=67890",
        ),
        (
            "https://facebook.com/zuck?fbclid=123",
            "https://facebook.com/zuck",
        ),
        (
            "https://m.facebook.com/zuck?fbclid=xyz",
            "https://facebook.com/zuck",
        ),
        (
            "https://mobile.twitter.com/jack?s=20",
            "https://x.com/jack",
        ),
        (
            "https://m.youtube.com/@mkbhd",
            "https://youtube.com/@mkbhd",
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
        ("https://m.facebook.com/profile.php?id=100012345", "Facebook", "id:100012345"),
        ("https://facebook.com/Profile.php?ID=100012345", "Facebook", "id:100012345"),
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


def test_facebook_canonical_url_identity_differentiation() -> None:
    """CRITICAL REGRESSION TEST: Verify Facebook identity query parameters are preserved and distinct."""
    fb_user_1_a = "https://www.facebook.com/profile.php?id=12345&utm_source=newsfeed&fbclid=abc"
    fb_user_1_b = "https://m.facebook.com/Profile.php?ID=12345&ref=bookmarks"
    fb_user_2 = "https://www.facebook.com/profile.php?id=67890&utm_medium=email"

    canon_1_a = canonical_url(fb_user_1_a)
    canon_1_b = canonical_url(fb_user_1_b)
    canon_2 = canonical_url(fb_user_2)

    # Same identity with different tracking parameters produces identical canonical URL
    assert canon_1_a == "https://facebook.com/profile.php?id=12345"
    assert canon_1_b == "https://facebook.com/profile.php?id=12345"
    assert canon_1_a == canon_1_b

    # Different identities produce strictly different canonical URLs
    assert canon_2 == "https://facebook.com/profile.php?id=67890"
    assert canon_1_a != canon_2

