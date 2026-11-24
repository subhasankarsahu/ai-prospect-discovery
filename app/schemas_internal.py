"""Internal data schemas for search results, candidate discovery, and platform worker outcomes."""

from pydantic import BaseModel, Field


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
