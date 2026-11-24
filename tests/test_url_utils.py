"""Unit tests for URL normalization and security validation utilities."""

from app.utils.url_utils import is_valid_platform_host, normalize_canonical_url


def test_valid_platform_host_standard() -> None:
    """Verify standard valid platform hosts."""
    allowed = {"linkedin.com", "x.com", "twitter.com"}
    assert is_valid_platform_host("https://linkedin.com/in/test", allowed) is True
    assert is_valid_platform_host("https://www.linkedin.com/in/test", allowed) is True
    assert is_valid_platform_host("https://in.linkedin.com/in/test", allowed) is True
    assert is_valid_platform_host("https://x.com/username", allowed) is True
    assert is_valid_platform_host("http://twitter.com/username", allowed) is True


def test_reject_lookalike_domains() -> None:
    """Verify lookalike and deceptive hostnames are rejected."""
    allowed = {"linkedin.com", "x.com", "instagram.com"}
    assert is_valid_platform_host("https://linkedin.com.attacker.com/in/test", allowed) is False
    assert is_valid_platform_host("https://x.com.phishing.io/user", allowed) is False
    assert is_valid_platform_host("https://instagram.com.fake-site.org/user", allowed) is False
    assert is_valid_platform_host("https://notlinkedin.com/in/test", allowed) is False


def test_reject_embedded_credentials() -> None:
    """Verify URLs with embedded credentials are strictly rejected."""
    allowed = {"linkedin.com", "x.com"}
    assert is_valid_platform_host("https://admin:password@linkedin.com/in/test", allowed) is False
    assert is_valid_platform_host("https://user@x.com/profile", allowed) is False


def test_reject_invalid_and_non_standard_ports() -> None:
    """Verify non-standard ports and malformed ports are rejected."""
    allowed = {"linkedin.com"}
    assert is_valid_platform_host("https://linkedin.com:443/in/test", allowed) is True
    assert is_valid_platform_host("http://linkedin.com:80/in/test", allowed) is True
    assert is_valid_platform_host("https://linkedin.com:8080/in/test", allowed) is False
    assert is_valid_platform_host("https://linkedin.com:999999/in/test", allowed) is False


def test_reject_unsupported_schemes_and_malformed_urls() -> None:
    """Verify non-HTTP(S) schemes and malformed URLs are rejected safely."""
    allowed = {"linkedin.com"}
    assert is_valid_platform_host("javascript:alert(1)//https://linkedin.com/in/test", allowed) is False
    assert is_valid_platform_host("ftp://linkedin.com/in/test", allowed) is False
    assert is_valid_platform_host("https://[::invalid]/in/test", allowed) is False
    assert is_valid_platform_host("not-a-url", allowed) is False


def test_normalize_canonical_url_tracking_parameters() -> None:
    """Verify tracking parameters are purged while URL path is preserved."""
    url = "https://x.com/sama?utm_source=twitter&utm_medium=social&ref_src=twsrc%5Egoogle"
    normalized = normalize_canonical_url(url)
    assert normalized == "https://x.com/sama"


def test_normalize_canonical_url_facebook_identity_preserved() -> None:
    """Verify Facebook profile.php preserves 'id' parameter while stripping tracking."""
    url = "https://facebook.com/profile.php?id=100001234567890&utm_source=fb&fbclid=abc123xyz"
    normalized = normalize_canonical_url(url, platform_name="Facebook")
    assert normalized == "https://facebook.com/profile.php?id=100001234567890"


def test_normalize_canonical_url_facebook_no_collision() -> None:
    """Verify distinct profile IDs do not collide after canonicalization."""
    url1 = "https://facebook.com/profile.php?id=11111&fbclid=abc"
    url2 = "https://facebook.com/profile.php?id=22222&fbclid=xyz"
    assert normalize_canonical_url(url1) != normalize_canonical_url(url2)
    assert normalize_canonical_url(url1) == "https://facebook.com/profile.php?id=11111"
    assert normalize_canonical_url(url2) == "https://facebook.com/profile.php?id=22222"


def test_normalize_canonical_url_facebook_vanity_strips_params() -> None:
    """Verify vanity Facebook profiles strip all query parameters."""
    url = "https://www.facebook.com/zuck/?ref=bookmarks&fbclid=xyz"
    normalized = normalize_canonical_url(url, platform_name="Facebook")
    assert normalized == "https://facebook.com/zuck"


def test_normalize_canonical_url_trailing_slash_and_fragment() -> None:
    """Verify trailing slashes and fragments are stripped cleanly."""
    url = "https://www.linkedin.com/in/johndoe/#experience"
    normalized = normalize_canonical_url(url)
    assert normalized == "https://linkedin.com/in/johndoe"
