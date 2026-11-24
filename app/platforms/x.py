"""X (formerly Twitter) platform source module."""

import re
from urllib.parse import urlsplit

from app.platforms.base import PlatformSource
from app.schemas import QueryIntent
from app.utils.url_utils import is_valid_platform_host

X_HANDLE_REGEX = re.compile(r"^[a-zA-Z0-9_]{1,15}$")
X_RESERVED_PATHS: set[str] = {
    "home",
    "explore",
    "notifications",
    "messages",
    "search",
    "hashtag",
    "i",
    "settings",
    "intent",
    "tos",
    "privacy",
    "about",
    "login",
    "signup",
    "share",
}


class XPlatform(PlatformSource):
    """X/Twitter search query builder and profile classifier."""

    @property
    def name(self) -> str:
        """Display name."""
        return "X"

    @property
    def allowed_domains(self) -> list[str]:
        """Allowed domains."""
        return ["x.com", "twitter.com"]

    def build_query(self, intent: QueryIntent) -> str:
        """Build X/Twitter search query targeting user handles."""
        terms = self._compose_base_terms(intent)
        terms.append("(site:x.com OR site:twitter.com)")
        return " ".join(terms)

    def is_profile_url(self, url: str) -> bool:
        """Determine if URL is a valid X/Twitter user profile."""
        if not is_valid_platform_host(url, set(self.allowed_domains)):
            return False

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return False

        path = parsed.path.strip("/")
        if not path or "/" in path:
            return False

        if path.lower() in X_RESERVED_PATHS:
            return False

        return bool(X_HANDLE_REGEX.match(path))
