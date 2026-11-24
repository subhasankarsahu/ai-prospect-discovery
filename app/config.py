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
        description="Google Gemini API key for discovery and extraction",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Model identifier to use with the Gemini provider",
    )
    tavily_api_key: str = Field(
        default="",
        description="Tavily API key for search engine querying",
    )
    request_timeout_seconds: int = Field(
        default=30,
        description="Default timeout in seconds for outgoing HTTP requests",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached application settings singleton instance."""
    return Settings()
