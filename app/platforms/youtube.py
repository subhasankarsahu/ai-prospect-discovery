"""YouTube platform source module."""

import re
from urllib.parse import urlsplit

from app.platforms.base import PlatformSource
from app.schemas import QueryIntent
from app.utils.url_utils import is_valid_platform_host

YT_HANDLE_REGEX = re.compile(r"^/@([a-zA-Z0-9_\-\.]+)$")
YT_CHANNEL_REGEX = re.compile(r"^/channel/(UC[a-zA-Z0-9_\-]+)$")
YT_CUSTOM_REGEX = re.compile(r"^/(c|user)/([a-zA-Z0-9_\-\.]+)$")
YT_EXCLUDED_PATHS: set[str] = {
    "watch",
    "shorts",
    "results",
    "feed",
    "playlist",
    "live",
    "gaming",
    "embed",
}


class YouTubePlatform(PlatformSource):
    """YouTube search query builder and channel/handle classifier."""

    @property
    def name(self) -> str:
        """Display name."""
        return "YouTube"

    @property
    def allowed_domains(self) -> list[str]:
        """Allowed domains."""
        return ["youtube.com"]

    def build_query(self, intent: QueryIntent) -> str:
        """Build YouTube search query targeting channels and handles."""
        terms = self._compose_base_terms(intent)
        terms.append("(site:youtube.com/@ OR site:youtube.com/c/ OR site:youtube.com/channel/)")
        return " ".join(terms)

    def is_profile_url(self, url: str) -> bool:
        """Determine if URL is a valid YouTube channel or creator profile."""
        if not is_valid_platform_host(url, set(self.allowed_domains)):
            return False

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return False

        path = parsed.path.rstrip("/")
        first_segment = path.strip("/").split("/")[0].lower() if path.strip("/") else ""
        if first_segment in YT_EXCLUDED_PATHS:
            return False

        if YT_HANDLE_REGEX.match(path):
            return True
        if YT_CHANNEL_REGEX.match(path):
            return True
        return bool(YT_CUSTOM_REGEX.match(path))
