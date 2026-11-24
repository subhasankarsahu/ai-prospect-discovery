"""Input data validators for emails, phone numbers, and profile URLs."""

import ipaddress
import logging
import re
from urllib.parse import urlsplit

import phonenumbers

logger = logging.getLogger(__name__)

# RFC 5322 compliant practical email pattern
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Placeholder domains that must always be rejected
PLACEHOLDER_DOMAINS: set[str] = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "test.org",
    "domain.com",
    "yourdomain.com",
    "sample.com",
    "placeholder.com",
}

# Officially supported social platform domains
SUPPORTED_PLATFORM_DOMAINS: set[str] = {
    "linkedin.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "instagram.com",
    "threads.net",
    "facebook.com",
}


def validate_email(text: str) -> str | None:
    """Validate and normalize an email address.

    Args:
        text: Candidate email string.

    Returns:
        Normalized lowercase email string, or None if invalid or placeholder.
    """
    if not text or not isinstance(text, str):
        return None

    clean = text.strip().lower()
    if not clean or len(clean) > 254:
        return None

    # Disallow embedded whitespace or newlines
    if any(ch.isspace() for ch in clean):
        return None

    if not EMAIL_REGEX.match(clean):
        return None

    try:
        local_part, domain_part = clean.rsplit("@", 1)
    except ValueError:
        return None

    if not local_part or not domain_part:
        return None

    # Reject placeholder domains or subdomains of placeholder domains
    if domain_part in PLACEHOLDER_DOMAINS or any(
        domain_part.endswith("." + d) for d in PLACEHOLDER_DOMAINS
    ):
        return None

    # TLD sanity check: must contain at least 2 characters and no digits only
    tld = domain_part.rsplit(".", 1)[-1]
    if len(tld) < 2 or tld.isdigit():
        return None

    return clean


def validate_phone(text: str, default_region: str = "US") -> str | None:
    """Validate a phone number and return its standard E.164 representation.

    Args:
        text: Raw phone number string.
        default_region: Two-letter ISO region code to interpret national numbers.

    Returns:
        Formatted E.164 string (e.g. +14155552671) if valid; None otherwise.
    """
    if not text or not isinstance(text, str):
        return None

    stripped = text.strip()
    if not stripped:
        return None

    try:
        parsed_number = phonenumbers.parse(stripped, default_region.strip().upper())
        if phonenumbers.is_valid_number(parsed_number):
            return phonenumbers.format_number(
                parsed_number, phonenumbers.PhoneNumberFormat.E164
            )
    except phonenumbers.NumberParseException:
        return None

    return None


def validate_profile_url(url: str) -> bool:
    """Verify that a URL is a secure HTTPS link to an allowed social platform host.

    Args:
        url: Raw candidate URL string.

    Returns:
        True if the URL passes all security and domain checks; False otherwise.
    """
    if not url or not isinstance(url, str):
        return False

    clean_url = url.strip()
    try:
        parsed = urlsplit(clean_url)
    except ValueError:
        return False

    # 1. Enforce HTTPS scheme strictly
    if parsed.scheme.lower() != "https":
        return False

    # 2. Reject embedded credentials / userinfo
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return False

    # 3. Reject missing or malformed hostname
    hostname = parsed.hostname
    if not hostname:
        return False
    hostname = hostname.lower()

    # 4. Reject IP addresses, localhost, and internal/local network names
    try:
        ipaddress.ip_address(hostname)
        return False  # Host is an IP address
    except ValueError:
        pass  # Host is a named domain, continue

    if hostname == "localhost" or hostname.endswith((".local", ".internal")):
        return False

    # 5. Reject non-default ports (port must be None or 443 for HTTPS)
    try:
        port = parsed.port
        if port is not None and port != 443:
            return False
    except ValueError:
        return False

    # 6. Validate exact allowed domain or valid dot-bounded subdomain
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in SUPPORTED_PLATFORM_DOMAINS
    )
