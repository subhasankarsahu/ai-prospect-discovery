"""Regression tests for fixture sanitization and privacy verification."""

from pathlib import Path

import pytest

from scripts.sanitize_fixtures import sanitize_data, sanitize_text, verify_privacy

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_sanitize_unformatted_indian_phone() -> None:
    """Verify unformatted 10-digit Indian phone numbers (starting 6-9) are redacted."""
    text1 = "Call Now 9205118443 for free consultation"
    assert sanitize_text(text1) == "Call Now REDACTED for free consultation"

    text2 = "Contact: 9876543210 immediately"
    assert sanitize_text(text2) == "Contact: REDACTED immediately"

    text3 = "Direct mobile 8123456789."
    assert sanitize_text(text3) == "Direct mobile REDACTED."


def test_sanitize_international_numbers() -> None:
    """Verify international phone numbers with country codes are redacted."""
    text1 = "Delhi office: +91 98765 43210"
    assert sanitize_text(text1) == "Delhi office: REDACTED"

    text2 = "Dubai hotline: +971 4 123 4567"
    assert sanitize_text(text2) == "Dubai hotline: REDACTED"

    text3 = "Berlin branch: +49 30 123456"
    assert sanitize_text(text3) == "Berlin branch: REDACTED"


def test_sanitize_us_formatted_phone() -> None:
    """Verify US formatted numbers in various standard representations are redacted."""
    samples = [
        ("NYC office: (212) 202-1431", "NYC office: REDACTED"),
        ("Call 212-202-1431 today", "Call REDACTED today"),
        ("Phone: 212.202.1431", "Phone: REDACTED"),
        ("Toll free: +1 800 555 0199", "Toll free: REDACTED"),
    ]
    for orig, expected in samples:
        assert sanitize_text(orig) == expected


def test_sanitize_uk_phone() -> None:
    """Verify UK telephone and mobile numbers are redacted."""
    samples = [
        ("London office: +44 20 7946 0991", "London office: REDACTED"),
        ("UK local: 020 7946 0991", "UK local: REDACTED"),
        ("Mobile: +44 7911 123456", "Mobile: REDACTED"),
        ("Direct: 07911 123456", "Direct: REDACTED"),
    ]
    for orig, expected in samples:
        assert sanitize_text(orig) == expected


def test_sanitize_whatsapp_phone_urls() -> None:
    """Verify phone numbers embedded in WhatsApp URLs are redacted to safe sentinels."""
    samples = [
        ("Message us: https://wa.me/919205118443", "Message us: https://wa.me/REDACTED"),
        ("Chat on wa.me/+12122021431 now", "Chat on https://wa.me/REDACTED now"),
        (
            "Contact: https://api.whatsapp.com/send?phone=447911123456",
            "Contact: https://wa.me/REDACTED",
        ),
    ]
    for orig, expected in samples:
        assert sanitize_text(orig) == expected


def test_preserve_facebook_profile_ids() -> None:
    """Verify Facebook numeric identity parameters in profile.php?id= are preserved."""
    url = "https://facebook.com/profile.php?id=100012345&ref=bookmarks"
    assert sanitize_text(url) == url

    snippet = "Check out my profile at https://m.facebook.com/profile.php?id=6789012345 and connect"
    assert sanitize_text(snippet) == snippet


def test_preserve_x_status_ids() -> None:
    """Verify X/Twitter status IDs are preserved for replay tweet inspection."""
    url = "https://x.com/gcfootball/status/1989667774009049234"
    assert sanitize_text(url) == url

    snippet = "See the announcement: https://twitter.com/CelticFC/status/1770097470959210956"
    assert sanitize_text(snippet) == snippet


def test_preserve_numbers_embedded_in_urls_and_identifiers() -> None:
    """Verify URLs, channels, ports, view counts, and timestamps are not corrupted."""
    samples = [
        "https://www.youtube.com/channel/UC1234567890123456789012",
        "https://example.com/posts/item-100200300",
        "http://localhost:8000/docs",
        "2025-11-15T12:12:18+00:00",
        "Views: 1925, Likes: 12, Reposts: 8, Bookmarks: 0",
    ]
    for s in samples:
        assert sanitize_text(s) == s


def test_preserve_already_redacted_values() -> None:
    """Verify idempotent behavior when text already contains REDACTED markers."""
    text = "Email: REDACTED, Phone: REDACTED, WhatsApp: https://wa.me/REDACTED"
    assert sanitize_text(text) == text


def test_sanitize_data_nested_structures() -> None:
    """Verify sanitize_data recursively scrubs nested dicts and lists."""
    data = {
        "candidate": {
            "name": "Jane Doe",
            "email": "jane@company.com",
            "phones": ["+1 212 555 0100", "9205118443"],
            "snippet": "Call now: 9205118443 or email jane@company.com",
            "profile_url": "https://facebook.com/profile.php?id=100099999",
        }
    }
    sanitized = sanitize_data(data)
    cand = sanitized["candidate"]
    assert cand["name"] == "Jane Doe"
    assert cand["email"] == "REDACTED"
    assert cand["phones"] == ["REDACTED", "REDACTED"]
    assert "9205118443" not in cand["snippet"]
    assert "jane@company.com" not in cand["snippet"]
    assert cand["profile_url"] == "https://facebook.com/profile.php?id=100099999"


def test_verify_privacy_raises_on_leaked_contacts() -> None:
    """Verify verify_privacy raises ValueError on any unredacted contact signal."""
    leaks = [
        ('{"snippet": "Call 9205118443 now"}', "unredacted 10-digit number"),
        ('{"snippet": "Call (212) 202-1431 now"}', "unredacted phone (US)"),
        ('{"snippet": "London office: +44 20 7946 0991"}', "unredacted phone (GB)"),
        ('{"snippet": "Contact direct@personalmail.com"}', "unredacted email"),
        ('{"wa": "https://wa.me/+919876543210"}', "unredacted WhatsApp URL"),
        ('{"key": "AIzaSyD-exampleGoogleKey123"}', "API key or auth token"),
    ]
    for json_str, expected_desc in leaks:
        with pytest.raises(ValueError) as exc_info:
            verify_privacy(json_str, slug="test_leak")
        assert "Privacy breach" in str(exc_info.value)


def test_verify_privacy_passes_all_committed_fixtures() -> None:
    """Verify all 5 committed JSON fixture files pass the hardened verify_privacy check."""
    slugs = [
        "football_lovers_washington_dc",
        "digital_marketing_owners_new_york",
        "startup_founders_london",
        "cricket_lovers_ahmedabad",
        "restaurant_owners_dubai",
    ]
    for slug in slugs:
        fixture_path = FIXTURES_DIR / f"{slug}.json"
        assert fixture_path.exists(), f"Fixture missing: {fixture_path}"
        content = fixture_path.read_text(encoding="utf-8")
        # Must not raise ValueError
        verify_privacy(content, slug=slug)
