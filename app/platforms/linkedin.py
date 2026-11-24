"""LinkedIn platform source module."""

import re
from urllib.parse import urlsplit

from app.platforms.base import PlatformSource
from app.schemas import QueryIntent
from app.utils.url_utils import is_valid_platform_host

LINKEDIN_PROFILE_REGEX = re.compile(r"^/in/([a-zA-Z0-9_\-%]+)$")


class LinkedInPlatform(PlatformSource):
    """LinkedIn search query builder and profile classifier."""

    @property
    def name(self) -> str:
        """Display name."""
        return "LinkedIn"

    @property
    def allowed_domains(self) -> list[str]:
        """Allowed domains."""
        return ["linkedin.com"]

    def build_query(self, intent: QueryIntent) -> str:
        """Build LinkedIn search query targeting /in/ profile slugs."""
        terms = self._compose_base_terms(intent)
        terms.append("site:linkedin.com/in")
        return " ".join(terms)

    def is_profile_url(self, url: str) -> bool:
        """Determine if URL is a valid LinkedIn personal profile."""
        if not is_valid_platform_host(url, set(self.allowed_domains)):
            return False

        try:
            parsed = urlsplit(url.strip())
        except ValueError:
            return False

        path = parsed.path.rstrip("/")
        match = LINKEDIN_PROFILE_REGEX.match(path)
        if not match:
            return False

        slug = match.group(1).lower()
        # Reject non-profile reserved subpaths
        return slug not in ("company", "school", "posts", "pulse", "jobs", "feed", "learning", "groups")
