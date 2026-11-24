"""URL normalization, security validation, and identity parameter handling."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking parameters unconditionally stripped across all platforms
UNIVERSAL_TRACKING_PARAMS: set[str] = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "zanpid",
    "ref",
    "ref_src",
    "ref_url",
    "source",
    "feature",
    "_ga",
    "_gl",
    "__twitter_impression",
    "ocid",
}


def is_valid_platform_host(url: str, allowed_domains: set[str]) -> bool:
    """Validate that URL scheme, credentials, port, and domain conform to platform requirements.

    Args:
        url: Raw candidate URL string.
        allowed_domains: Set of exact allowed domains (e.g. {"linkedin.com"}).

    Returns:
        True if the host is valid and safe; False otherwise.
    """
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return False

    # 1. Enforce HTTP/HTTPS scheme
    if parsed.scheme.lower() not in ("http", "https"):
        return False

    # 2. Reject embedded credentials (user:pass@host)
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return False

    # 3. Reject missing hostname
    hostname = parsed.hostname
    if not hostname:
        return False
    hostname = hostname.lower()

    # 4. Reject invalid or non-standard ports
    try:
        port = parsed.port
        if port is not None and port not in (80, 443):
            return False
    except ValueError:
        return False

    # 5. Validate exact allowed domain or valid subdomain
    return any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in allowed_domains
    )


def normalize_canonical_url(url: str, platform_name: str | None = None) -> str:
    """Normalize a profile URL into its canonical representation.

    Purges universal tracking parameters, forces https, normalizes hostname,
    preserves identity-defining parameters (e.g. Facebook profile.php?id=...),
    and strips URL fragments and trailing slashes.

    Args:
        url: Raw profile URL string.
        platform_name: Optional platform name for specialized parameter rules.

    Returns:
        Canonical URL string.
    """
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    scheme = "https"
    hostname = (parsed.hostname or "").lower()

    # Standardize www. prefix
    netloc = hostname
    if netloc.startswith("www.") and len(netloc) > 4:
        netloc = netloc[4:]

    # Normalize platform subdomains and aliases to canonical roots
    if netloc in ("facebook.com", "fb.com") or netloc.endswith((".facebook.com", ".fb.com")):
        netloc = "facebook.com"
    elif netloc in ("twitter.com", "x.com") or netloc.endswith((".twitter.com", ".x.com")):
        netloc = "x.com"
    elif netloc == "linkedin.com" or netloc.endswith(".linkedin.com"):
        netloc = "linkedin.com"
    elif netloc == "instagram.com" or netloc.endswith(".instagram.com"):
        netloc = "instagram.com"
    elif netloc == "youtube.com" or netloc.endswith(".youtube.com"):
        netloc = "youtube.com"
    elif netloc == "threads.net" or netloc.endswith(".threads.net"):
        netloc = "threads.net"

    # Normalize path: strip trailing slash unless path is root or empty
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    is_facebook = (
        platform_name == "Facebook"
        or netloc == "facebook.com"
    )
    is_fb_profile_php = is_facebook and path.lower() == "/profile.php"
    if is_fb_profile_php:
        path = "/profile.php"

    # Parse and clean query parameters
    raw_query_params = parse_qsl(parsed.query, keep_blank_values=True)
    cleaned_params: list[tuple[str, str]] = []
    seen_id = False

    for key, val in raw_query_params:
        lower_key = key.lower()

        # Purge universal tracking parameters
        if lower_key in UNIVERSAL_TRACKING_PARAMS or lower_key.startswith("utm_"):
            continue

        # Platform-specific retention
        if is_fb_profile_php:
            # Preserve Facebook's id parameter canonically with lowercase key and first occurrence
            if lower_key == "id" and not seen_id:
                clean_id = val.strip().rstrip("/")
                if clean_id:
                    cleaned_params.append(("id", clean_id))
                    seen_id = True
        else:
            # Non-Facebook or vanity Facebook profiles do not use query parameters
            pass

    new_query = urlencode(cleaned_params) if cleaned_params else ""

    # Fragments are unconditionally stripped for canonical URLs
    return urlunsplit((scheme, netloc, path, new_query, ""))
