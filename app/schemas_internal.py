"""Internal data schemas for search results, candidate discovery, and platform worker outcomes."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import SocialLink


class TavilySearchResult(BaseModel):
    """Raw result item returned from Tavily Search API."""

    url: str = Field(description="URL of the web document")
    title: str = Field(default="", description="Title of the web document")
    snippet: str = Field(default="", description="Text snippet or content extracted by search")


class RawCandidate(BaseModel):
    """Unverified raw candidate profile discovered during multi-platform search."""

    source_platform: str = Field(description="Originating platform name")
    canonical_url: str = Field(description="Normalized canonical profile URL")
    title: str = Field(default="", description="Page title from search result")
    snippet: str = Field(default="", description="Contextual search snippet")
    search_query: str = Field(description="The exact search query that retrieved this candidate")


class PlatformOutcome(BaseModel):
    """Structured outcome for an individual platform discovery worker."""

    platform_name: str = Field(description="Name of the platform executed")
    success: bool = Field(description="Whether the platform search completed successfully")
    candidates: list[RawCandidate] = Field(
        default_factory=list,
        description="List of raw candidate profiles discovered and validated",
    )
    error_type: str | None = Field(
        default=None,
        description="Error class name if the platform search failed",
    )
    error_message: str | None = Field(
        default=None,
        description="High-level description of the error if failed",
    )


class CandidateClassification(BaseModel):
    """Raw relevance classification item returned by LLM for a candidate."""

    candidate_index: int = Field(description="Zero-based index of candidate within the batch")
    is_individual_person: bool = Field(description="Whether the result represents an individual human")
    name_as_written: str = Field(description="Person name as written verbatim in the candidate text")
    interest_supported: bool = Field(description="Whether the candidate supports the requested interest")
    location_supported: bool = Field(description="Whether the candidate supports the requested location")
    confidence: Literal["low", "medium", "high"] = Field(description="Confidence tier")
    reason: str = Field(description="One sentence explaining the classification")


class VerifiedCandidate(BaseModel):
    """Candidate profile verified by LLM relevance classification and code-side evidence checks."""

    raw_candidate: RawCandidate = Field(description="Original discovered raw candidate")
    verified_name: str = Field(description="Verified display name verified verbatim from title/snippet")
    source_platform: str = Field(description="Originating platform name")
    canonical_url: str = Field(description="Preserved canonical URL")
    location: str | None = Field(default=None, description="Location text if verified in snippet/title")
    confidence: str = Field(default="medium", description="Relevance confidence level")
    reason: str = Field(default="", description="Classification reason")
    contacts: list[SocialLink] = Field(default_factory=list, description="Page-scoped contact details")
