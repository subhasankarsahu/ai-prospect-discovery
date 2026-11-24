"""Application configuration loaded from environment variables using pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application runtime configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = Field(
        default="gemini",
        description="Active LLM provider identifier",
    )
    gemini_api_key: str = Field(
        default="",
        repr=False,
        description="Google Gemini API key for discovery and extraction",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Model identifier to use with the Gemini provider",
    )
    tavily_api_key: str = Field(
        default="",
        repr=False,
        description="Tavily API key for search engine querying",
    )
    request_timeout_seconds: int = Field(
        default=30,
        description="Default timeout in seconds for outgoing HTTP requests",
    )
    search_cache_enabled: bool = Field(
        default=True,
        description="Enable local disk caching for search responses",
    )
    search_cache_dir: str = Field(
        default=".cache/search",
        description="Directory path for local search cache storage",
    )
    phone_default_region: str = Field(
        default="US",
        description="Default two-letter ISO region code for national phone number parsing",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached application settings singleton instance."""
    return Settings()
