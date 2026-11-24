"""Unit tests for email, phone, and profile URL validators."""

import pytest

from app.utils.validators import validate_email, validate_phone, validate_profile_url


@pytest.mark.parametrize(
    "input_email, expected",
    [
        ("user@company.org", "user@company.org"),
        ("USER@COMPANY.ORG", "user@company.org"),
        ("  first.last+tag@sub.domain.co.uk  ", "first.last+tag@sub.domain.co.uk"),
        ("jane_doe123@tech.io", "jane_doe123@tech.io"),
    ],
)
def test_validate_email_valid(input_email: str, expected: str) -> None:
    """Verify that legitimate email addresses are normalized to lowercase."""
    assert validate_email(input_email) == expected


@pytest.mark.parametrize(
    "invalid_email",
    [
        "",
        "   ",
        "plainaddress",
        "@missinglocal.com",
        "missingdomain@",
        "two@@signs.com",
        "embedded space@domain.com",
        "user@.leadingdot.com",
        "user@trailingdot.com.",
        "user@domain..com",
        "user@domain",
        "user@domain.c",
        "user@domain.123",
        "user@example.com",
        "user@test.com",
        "user@domain.com",
        "user@yourdomain.com",
        "user@sample.com",
        "user@sub.example.com",
        "user@mail.test.com",
    ],
)
def test_validate_email_invalid_and_placeholders(invalid_email: str) -> None:
    """Verify that malformed and placeholder domain emails return None."""
    assert validate_email(invalid_email) is None


@pytest.mark.parametrize(
    "phone_input, region, expected_e164",
    [
        ("415-555-2671", "US", "+14155552671"),
        ("(415) 555-2671", "US", "+14155552671"),
        ("+1 415 555 2671", "US", "+14155552671"),
        ("+44 20 7946 0991", "GB", "+442079460991"),
        ("020 7946 0991", "GB", "+442079460991"),
        ("+49 30 123456", "DE", "+4930123456"),
    ],
)
def test_validate_phone_valid(phone_input: str, region: str, expected_e164: str) -> None:
    """Verify valid phone numbers return formatted E.164 strings."""
    assert validate_phone(phone_input, default_region=region) == expected_e164


@pytest.mark.parametrize(
    "invalid_phone, region",
    [
        ("", "US"),
        ("   ", "US"),
        ("12345", "US"),
        ("abcdefg", "US"),
        ("+1 555 123", "US"),
        ("0000000000", "US"),
        ("not a phone number", "GB"),
    ],
)
def test_validate_phone_invalid(invalid_phone: str, region: str) -> None:
    """Verify invalid phone numbers return None without throwing exceptions."""
    assert validate_phone(invalid_phone, default_region=region) is None


@pytest.mark.parametrize(
    "valid_url",
    [
        "https://linkedin.com/in/john-doe",
        "https://www.linkedin.com/in/john-doe",
        "https://x.com/elonmusk",
        "https://twitter.com/jack",
        "https://youtube.com/@mkbhd",
        "https://www.youtube.com/channel/UC123456",
        "https://instagram.com/zuck",
        "https://threads.net/@zuck",
        "https://facebook.com/profile.php?id=100012345",
        "https://facebook.com/zuck",
    ],
)
def test_validate_profile_url_valid(valid_url: str) -> None:
    """Verify HTTPS social platform profile URLs are accepted."""
    assert validate_profile_url(valid_url) is True


@pytest.mark.parametrize(
    "invalid_url",
    [
        "",
        "   ",
        "http://linkedin.com/in/john-doe",  # HTTP rejected (HTTPS only)
        "ftp://x.com/user",
        "https://user:pass@x.com/user",  # Embedded credentials
        "https://127.0.0.1/in/john",  # IP address
        "https://192.168.1.1/user",  # Private IP
        "https://localhost/in/john",  # Localhost
        "https://server.local/in/john",  # .local
        "https://internal/in/john",  # No dot
        "https://linkedin.com:8080/in/john",  # Non-default port
        "https://x.com:80/user",  # Non-default port for HTTPS
        "https://linkedin.com.attacker.com/in/john",  # Lookalike subdomain
        "https://fake-x.com/user",  # Lookalike domain
        "https://github.com/torvalds",  # Unsupported platform
        "https://medium.com/@someone",  # Unsupported platform
    ],
)
def test_validate_profile_url_invalid(invalid_url: str) -> None:
    """Verify that insecure, lookalike, credentials, and unsupported URLs are rejected."""
    assert validate_profile_url(invalid_url) is False
