"""Pydantic data schemas and validation models for the discovery API."""

from pydantic import BaseModel, Field, field_validator


class Location(BaseModel):
    """Geographic location details with city, state, and country."""

    city: str | None = Field(default=None, description="City name")
    state: str | None = Field(default=None, description="State or province name")
    country: str | None = Field(default=None, description="Country name")


class QueryIntent(BaseModel):
    """Structured query intent extracted from natural language search prompts."""

    is_prospect_query: bool = Field(
        default=True,
        description="Whether the query is looking for candidate people or organizations",
    )
    interest: str = Field(
        description="Core interest, topic, industry, or domain of the search",
    )
    audience: str | None = Field(
        default=None,
        description="Target audience or market persona",
    )
    location: Location | None = Field(
        default=None,
        description="Geographic location constraints",
    )
    target_type: str = Field(
        default="individual",
        description="Target prospect entity type (e.g., individual, company, founder)",
    )


class SocialLink(BaseModel):
    """Verified platform link for a prospect."""

    platform: str = Field(
        description="Name of the platform, e.g., linkedin, twitter, github",
    )
    link: str = Field(
        description="Direct public URL to the profile or page",
    )


class Prospect(BaseModel):
    """A discovered candidate prospect."""

    name: str = Field(
        description="Verified name of the individual or organization",
    )
    location: str | Location | None = Field(
        default=None,
        description="Location string or structured location object",
    )
    social_link: list[SocialLink] = Field(
        default_factory=list,
        description="List of verified social and professional profile links",
    )


class DiscoveryRequest(BaseModel):
    """Request payload for prospect discovery."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural language prompt for prospect discovery",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_whitespace(cls, value: str) -> str:
        """Ensure search query is not whitespace only."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Query cannot be empty or whitespace only")
        return stripped


class DiscoveryResponse(BaseModel):
    """API response model for prospect discovery results."""

    success: bool = Field(
        default=True,
        description="Indicates whether the discovery operation succeeded",
    )
    query: str = Field(
        description="Original search query passed in request",
    )
    total_prospects: int = Field(
        default=0,
        description="Total number of prospects returned",
    )
    prospects: list[Prospect] = Field(
        default_factory=list,
        description="List of verified discovered prospects",
    )


class HealthResponse(BaseModel):
    """Health status response model."""

    status: str = Field(
        default="healthy",
        description="Service health status indicator",
    )
