"""URL, name, and profile handle normalization utilities for identity resolution."""

import re
import unicodedata
from urllib.parse import parse_qsl, urlsplit

from app.platforms.facebook import FB_EXCLUDED_PATHS
from app.platforms.instagram import IG_EXCLUDED_PATHS
from app.platforms.threads import THREADS_EXCLUDED_PATHS
from app.platforms.x import X_RESERVED_PATHS
from app.utils.url_utils import normalize_canonical_url
from app.utils.validators import validate_profile_url

LINKEDIN_SLUG_REGEX = re.compile(r"^/in/([a-zA-Z0-9_\-%]+)/?$")
X_HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,15}$")
YT_HANDLE_REGEX = re.compile(r"^/@([a-zA-Z0-9_\-\.]+)$")
YT_CHANNEL_REGEX = re.compile(r"^/channel/(UC[a-zA-Z0-9_\-]+)$")
YT_CUSTOM_REGEX = re.compile(r"^/(?:c|user)/([a-zA-Z0-9_\-\.]+)$")
IG_HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_\.]{1,30}$")
THREADS_HANDLE_REGEX = re.compile(r"^@?([a-zA-Z0-9_\.]+)$")
FB_VANITY_REGEX = re.compile(r"^[a-zA-Z0-9\.\-_]{1,50}$")


def canonical_url(url: str) -> str:
    """Normalize a URL to its canonical standard form for identity resolution.

    Forces HTTPS, normalizes domain (lowercase, www removal, twitter->x mapping),
    preserves identity-defining parameters (e.g. Facebook profile.php?id=...),
    and strips tracking query parameters, trailing slashes, and fragments.

    Args:
        url: Raw candidate URL.

    Returns:
        Canonical URL string.
    """
    return normalize_canonical_url(url)


def normalize_name(name: str) -> str:
    """Normalize a person's display name for identity comparison only.

    Applies NFKC Unicode normalization, collapses multiple whitespaces,
    trims whitespace, and converts to lowercase. Preserves punctuation
    to prevent false name collision.

    Args:
        name: Raw display name string.

    Returns:
        Normalized lowercase name string for comparison.
    """
    if not name or not isinstance(name, str):
        return ""

    # NFKC Unicode normalization
    normalized = unicodedata.normalize("NFKC", name.strip())
    # Collapse multiple whitespace characters into a single space
    collapsed = re.sub(r"\s+", " ", normalized)
    return collapsed.strip().lower()


def extract_handle(url: str, platform: str) -> str | None:
    """Extract and normalize the user handle or channel identifier from a profile URL.

    Args:
        url: Validated public profile URL.
        platform: Platform name (e.g., 'LinkedIn', 'X', 'YouTube', 'Instagram', 'Threads', 'Facebook').

    Returns:
        Normalized lowercase handle/slug if valid; None otherwise.
    """
    if not url or not isinstance(url, str):
        return None

    # Verify that the URL is a safe, allowed HTTPS social profile URL
    if not validate_profile_url(url):
        return None

    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return None

    plat = platform.strip().lower()
    path = parsed.path.rstrip("/")

    if plat == "linkedin":
        match = LINKEDIN_SLUG_REGEX.match(parsed.path)
        if not match:
            return None
        slug = match.group(1).lower()
        if slug in ("company", "school", "posts", "pulse", "jobs", "feed", "learning", "groups"):
            return None
        return slug

    if plat in ("x", "twitter"):
        clean_path = path.strip("/")
        if not clean_path or "/" in clean_path:
            return None
        if clean_path.lower() in X_RESERVED_PATHS:
            return None
        if X_HANDLE_REGEX.match(clean_path):
            return clean_path.lower()
        return None

    if plat == "youtube":
        first_segment = path.strip("/").split("/")[0].lower() if path.strip("/") else ""
        if first_segment in ("watch", "shorts", "results", "feed", "playlist", "live", "gaming"):
            return None
        m_handle = YT_HANDLE_REGEX.match(path)
        if m_handle:
            return m_handle.group(1).lower()
        m_channel = YT_CHANNEL_REGEX.match(path)
        if m_channel:
            return m_channel.group(1).lower()
        m_custom = YT_CUSTOM_REGEX.match(path)
        if m_custom:
            return m_custom.group(1).lower()
        return None

    if plat == "instagram":
        clean_path = path.strip("/")
        if not clean_path or "/" in clean_path:
            return None
        if clean_path.lower() in IG_EXCLUDED_PATHS:
            return None
        if IG_HANDLE_REGEX.match(clean_path):
            return clean_path.lower()
        return None

    if plat == "threads":
        clean_path = path.strip("/")
        if not clean_path:
            return None
        segments = clean_path.split("/")
        first_segment = segments[0]
        if first_segment.lower() in THREADS_EXCLUDED_PATHS:
            return None
        if len(segments) > 1 and segments[1].lower() == "post":
            return None
        m_threads = THREADS_HANDLE_REGEX.match(first_segment)
        if m_threads:
            return m_threads.group(1).lower()
        return None

    if plat == "facebook":
        if path == "/profile.php":
            query_params = dict(parse_qsl(parsed.query))
            id_val = query_params.get("id", "")
            return f"id:{id_val}" if id_val.isdigit() and len(id_val) >= 4 else None

        clean_path = path.strip("/")
        if not clean_path or "/" in clean_path or clean_path.endswith(".php"):
            return None
        if clean_path.lower() in FB_EXCLUDED_PATHS:
            return None
        if FB_VANITY_REGEX.match(clean_path):
            return clean_path.lower()
        return None

    return None
