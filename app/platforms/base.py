"""Base abstract class for platform discovery modules."""

from abc import ABC, abstractmethod

from app.schemas import QueryIntent
from app.utils.url_utils import normalize_canonical_url


class PlatformSource(ABC):
    """Abstract base class for platform search query construction and URL classification."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Display name of the platform."""
        ...

    @property
    @abstractmethod
    def allowed_domains(self) -> list[str]:
        """Allowed domain names for this platform."""
        ...

    @abstractmethod
    def build_query(self, intent: QueryIntent) -> str:
        """Construct platform-specific search query from structured query intent."""
        ...

    @abstractmethod
    def is_profile_url(self, url: str) -> bool:
        """Verify whether a URL represents a genuine public profile on this platform."""
        ...

    def extract_canonical_url(self, url: str) -> str:
        """Normalize URL to its canonical form using platform-specific parameters."""
        return normalize_canonical_url(url, platform_name=self.name)

    def _compose_base_terms(self, intent: QueryIntent) -> list[str]:
        """Helper to collect and format query keywords from intent fields."""
        terms: list[str] = [f'"{intent.interest.strip()}"']

        if intent.target_type and intent.target_type.lower() not in ("individual", "other", "any", ""):
            terms.append(intent.target_type.strip())

        if intent.audience and intent.audience.strip():
            terms.append(intent.audience.strip())

        if intent.location:
            loc_parts = [
                part.strip()
                for part in (intent.location.city, intent.location.state, intent.location.country)
                if part and part.strip()
            ]
            if loc_parts:
                terms.append(" ".join(loc_parts))

        return terms
