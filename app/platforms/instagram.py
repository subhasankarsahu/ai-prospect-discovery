"""Instagram platform source module."""

import re
from urllib.parse import urlsplit

from app.platforms.base import PlatformSource
from app.schemas import QueryIntent
from app.utils.url_utils import is_valid_platform_host

IG_HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_\.]{1,30}$")
IG_EXCLUDED_PATHS: set[str] = {
    "p",
    "reel",
    "reels",
    "stories",
    "explore",
    "tv",
    "accounts",
    "direct",
    "developer",
    "legal",
    "about",
    "directory",
    "nametag",
}


class InstagramPlatform(PlatformSource):
    """Instagram search query builder and profile classifier."""

    @property
    def name(self) -> str:
        """Display name."""
        return "Instagram"

    @property
    def allowed_domains(self) -> list[str]:
        """Allowed domains."""
        return ["instagram.com"]

    def build_query(self, intent: QueryIntent) -> str:
        """Build Instagram search query targeting profile usernames."""
        terms = self._compose_base_terms(intent)
        terms.append("site:instagram.com")
        return " ".join(terms)

    def is_profile_url(self, url: str) -> bool:
        """Determine if URL is a valid Instagram user profile."""
        if not is_valid_platform_host(url, set(self.allowed_domains)):
            return False

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return False

        path = parsed.path.strip("/")
        if not path or "/" in path:
            return False

        if path.lower() in IG_EXCLUDED_PATHS:
            return False

        return bool(IG_HANDLE_REGEX.match(path))
