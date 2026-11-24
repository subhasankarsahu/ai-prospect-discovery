"""Threads platform source module."""

import re
from urllib.parse import urlsplit

from app.platforms.base import PlatformSource
from app.schemas import QueryIntent
from app.utils.url_utils import is_valid_platform_host

THREADS_HANDLE_REGEX = re.compile(r"^@([a-zA-Z0-9_\.]+)$")
THREADS_EXCLUDED_PATHS: set[str] = {
    "search",
    "settings",
    "terms",
    "privacy",
    "login",
}


class ThreadsPlatform(PlatformSource):
    """Threads search query builder and profile classifier."""

    @property
    def name(self) -> str:
        """Display name."""
        return "Threads"

    @property
    def allowed_domains(self) -> list[str]:
        """Allowed domains."""
        return ["threads.net"]

    def build_query(self, intent: QueryIntent) -> str:
        """Build Threads search query targeting @username profiles."""
        terms = self._compose_base_terms(intent)
        terms.append("site:threads.net/@")
        return " ".join(terms)

    def is_profile_url(self, url: str) -> bool:
        """Determine if URL is a valid Threads user profile."""
        if not is_valid_platform_host(url, set(self.allowed_domains)):
            return False

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return False

        path = parsed.path.strip("/")
        if not path:
            return False

        segments = path.split("/")
        first_segment = segments[0]

        if first_segment.lower() in THREADS_EXCLUDED_PATHS:
            return False

        # Exclude posts e.g. /@username/post/12345
        if len(segments) > 1 and segments[1].lower() == "post":
            return False

        return bool(THREADS_HANDLE_REGEX.match(first_segment))
