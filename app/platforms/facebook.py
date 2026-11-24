"""Facebook platform source module."""

import re
from urllib.parse import parse_qsl, urlsplit

from app.platforms.base import PlatformSource
from app.schemas import QueryIntent
from app.utils.url_utils import is_valid_platform_host

FB_VANITY_REGEX = re.compile(r"^[a-zA-Z0-9\.\-_]{1,50}$")
FB_EXCLUDED_PATHS: set[str] = {
    "groups",
    "events",
    "watch",
    "photo",
    "photos",
    "share",
    "sharer",
    "story.php",
    "login",
    "help",
    "marketplace",
    "pages",
    "home",
    "about",
    "privacy",
    "policies",
    "terms",
    "recover",
    "checkpoint",
}


class FacebookPlatform(PlatformSource):
    """Facebook search query builder and profile/page classifier."""

    @property
    def name(self) -> str:
        """Display name."""
        return "Facebook"

    @property
    def allowed_domains(self) -> list[str]:
        """Allowed domains."""
        return ["facebook.com"]

    def build_query(self, intent: QueryIntent) -> str:
        """Build Facebook search query targeting public pages and profiles."""
        terms = self._compose_base_terms(intent)
        terms.append("site:facebook.com")
        return " ".join(terms)

    def is_profile_url(self, url: str) -> bool:
        """Determine if URL is a valid Facebook profile or page."""
        if not is_valid_platform_host(url, set(self.allowed_domains)):
            return False

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return False

        path = parsed.path.rstrip("/")

        # Case 1: profile.php?id=<numeric_id>
        if path == "/profile.php":
            query_params = dict(parse_qsl(parsed.query))
            id_val = query_params.get("id", "")
            return bool(id_val.isdigit() and len(id_val) >= 4)

        # Case 2: Vanity username path e.g. /zuck
        clean_path = path.strip("/")
        if not clean_path or "/" in clean_path:
            return False

        # Reject any other .php scripts (e.g. photo.php, story.php, login.php)
        if clean_path.endswith(".php"):
            return False

        if clean_path.lower() in FB_EXCLUDED_PATHS:
            return False

        return bool(FB_VANITY_REGEX.match(clean_path))
