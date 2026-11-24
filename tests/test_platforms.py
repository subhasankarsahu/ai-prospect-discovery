"""Unit tests for platform query construction and URL classification."""

from app.platforms.facebook import FacebookPlatform
from app.platforms.instagram import InstagramPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.threads import ThreadsPlatform
from app.platforms.x import XPlatform
from app.platforms.youtube import YouTubePlatform
from app.schemas import Location, QueryIntent


def test_platform_query_building() -> None:
    """Verify dynamic query construction without hardcoded examples."""
    intent = QueryIntent(
        is_prospect_query=True,
        interest="quantum computing",
        audience="researchers",
        location=Location(city="Zurich", country="Switzerland"),
        target_type="scientist",
    )

    linkedin = LinkedInPlatform()
    x = XPlatform()
    youtube = YouTubePlatform()
    instagram = InstagramPlatform()
    threads = ThreadsPlatform()
    facebook = FacebookPlatform()

    l_query = linkedin.build_query(intent)
    assert '"quantum computing"' in l_query
    assert "scientist" in l_query
    assert "researchers" in l_query
    assert "Zurich Switzerland" in l_query
    assert "site:linkedin.com/in" in l_query

    x_query = x.build_query(intent)
    assert "(site:x.com OR site:twitter.com)" in x_query

    yt_query = youtube.build_query(intent)
    assert "site:youtube.com/@" in yt_query

    ig_query = instagram.build_query(intent)
    assert "site:instagram.com" in ig_query

    th_query = threads.build_query(intent)
    assert "site:threads.net/@" in th_query

    fb_query = facebook.build_query(intent)
    assert "site:facebook.com" in fb_query


def test_linkedin_url_classification() -> None:
    """Verify valid and invalid LinkedIn profile URLs (3+ valid, 3+ invalid, lookalike)."""
    p = LinkedInPlatform()

    # Valid
    assert p.is_profile_url("https://www.linkedin.com/in/satyanadella") is True
    assert p.is_profile_url("https://linkedin.com/in/john-doe-123/") is True
    assert p.is_profile_url("https://in.linkedin.com/in/jane_doe_99") is True

    # Invalid
    assert p.is_profile_url("https://www.linkedin.com/company/microsoft") is False
    assert p.is_profile_url("https://www.linkedin.com/posts/12345") is False
    assert p.is_profile_url("https://www.linkedin.com/jobs/view/999") is False
    assert p.is_profile_url("https://linkedin.com/feed") is False
    assert p.is_profile_url("https://linkedin.com.attacker.com/in/user") is False


def test_x_url_classification() -> None:
    """Verify valid and invalid X/Twitter profile URLs (3+ valid, 3+ invalid, lookalike)."""
    p = XPlatform()

    # Valid
    assert p.is_profile_url("https://x.com/sama") is True
    assert p.is_profile_url("https://twitter.com/elonmusk/") is True
    assert p.is_profile_url("https://www.x.com/karpathy") is True

    # Invalid
    assert p.is_profile_url("https://x.com/home") is False
    assert p.is_profile_url("https://x.com/explore") is False
    assert p.is_profile_url("https://x.com/sama/status/123456789") is False
    assert p.is_profile_url("https://x.com/search?q=ai") is False
    assert p.is_profile_url("https://x.com.attacker.com/user") is False


def test_youtube_url_classification() -> None:
    """Verify valid and invalid YouTube channel/handle URLs (3+ valid, 3+ invalid, lookalike)."""
    p = YouTubePlatform()

    # Valid
    assert p.is_profile_url("https://youtube.com/@mkbhd") is True
    assert p.is_profile_url("https://www.youtube.com/c/Veritasium") is True
    assert p.is_profile_url("https://youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw") is True
    assert p.is_profile_url("https://youtube.com/user/TEDtalksDirector") is True

    # Invalid
    assert p.is_profile_url("https://youtube.com/watch?v=dQw4w9WgXcQ") is False
    assert p.is_profile_url("https://www.youtube.com/shorts/12345abc") is False
    assert p.is_profile_url("https://youtube.com/results?search_query=ai") is False
    assert p.is_profile_url("https://youtube.com.phishing.net/@creator") is False


def test_instagram_url_classification() -> None:
    """Verify valid and invalid Instagram profile URLs (3+ valid, 3+ invalid, lookalike)."""
    p = InstagramPlatform()

    # Valid
    assert p.is_profile_url("https://www.instagram.com/zuck") is True
    assert p.is_profile_url("https://instagram.com/natgeo/") is True
    assert p.is_profile_url("https://instagram.com/openai.dev") is True

    # Invalid
    assert p.is_profile_url("https://instagram.com/p/C-xyz123/") is False
    assert p.is_profile_url("https://www.instagram.com/reel/C-abc456") is False
    assert p.is_profile_url("https://instagram.com/explore") is False
    assert p.is_profile_url("https://instagram.com.fake-site.org/user") is False


def test_threads_url_classification() -> None:
    """Verify valid and invalid Threads profile URLs (3+ valid, 3+ invalid, lookalike)."""
    p = ThreadsPlatform()

    # Valid
    assert p.is_profile_url("https://www.threads.net/@zuck") is True
    assert p.is_profile_url("https://threads.net/@mosseri/") is True
    assert p.is_profile_url("https://threads.net/@instagram") is True

    # Invalid
    assert p.is_profile_url("https://threads.net/@zuck/post/C-xyz123") is False
    assert p.is_profile_url("https://threads.net/search") is False
    assert p.is_profile_url("https://threads.net/settings") is False
    assert p.is_profile_url("https://threads.net.scam.com/@user") is False


def test_facebook_url_classification() -> None:
    """Verify valid and invalid Facebook profile URLs (3+ valid, 3+ invalid, lookalike)."""
    p = FacebookPlatform()

    # Valid
    assert p.is_profile_url("https://www.facebook.com/zuck") is True
    assert p.is_profile_url("https://facebook.com/profile.php?id=100001234567890") is True
    assert p.is_profile_url("https://facebook.com/Microsoft/") is True

    # Invalid
    assert p.is_profile_url("https://facebook.com/groups/123456789") is False
    assert p.is_profile_url("https://facebook.com/events/123456") is False
    assert p.is_profile_url("https://facebook.com/photo.php?fbid=123") is False
    assert p.is_profile_url("https://facebook.com/profile.php") is False  # Missing id parameter
    assert p.is_profile_url("https://facebook.com/profile.php?id=abc") is False  # Non-numeric id
    assert p.is_profile_url("https://facebook.com.hacker.io/zuck") is False
