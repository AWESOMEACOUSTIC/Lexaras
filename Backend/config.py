"""
Why this pattern?
- All secrets are validated at startup, not silently None at runtime
- Settings are typed — a missing API key is a startup crash, not a midnight incident
- Environment variables, .env files, and overrides all work transparently
- No dotenv calls scattered across every file — one load, everywhere

Usage:
    from config import settings
    client = SomeClient(api_key=settings.TAVILY_API_KEY)
"""

from __future__ import annotations

import logging
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application settings. Values are read from environment variables
    or a .env file in the project root. Missing required values raise
    a ValidationError at startup — fail fast, fail loudly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,       # MISTRAL_API_KEY == mistral_api_key
        extra="ignore",             # don't crash on unknown env vars
    )

    # LLM Providers
    MISTRAL_API_KEY: str = Field(..., description="Mistral AI API key")
    GROQ_API_KEY: str | None = Field(None, description="Groq API key (fallback LLM)")

    # Tool Providers
    TAVILY_API_KEY: str = Field(..., description="Tavily search API key")

    # Observability
    LANGCHAIN_API_KEY: str | None = Field(None, description="LangSmith tracing key")
    LANGCHAIN_TRACING_V2: bool = Field(False, description="Enable LangSmith tracing")
    LANGCHAIN_PROJECT: str = Field("lexaras", description="LangSmith project name")

    # Application 
    LOG_LEVEL: str = Field("INFO", description="Python logging level")
    ENVIRONMENT: str = Field("development", description="deployment environment: development | staging | production")

    @field_validator("MISTRAL_API_KEY", "TAVILY_API_KEY")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v.strip()

    @field_validator("LOG_LEVEL")
    @classmethod
    def valid_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {valid}, got {v!r}")
        return upper

    @field_validator("ENVIRONMENT")
    @classmethod
    def valid_environment(cls, v: str) -> str:
        valid = {"development", "staging", "production"}
        lower = v.lower()
        if lower not in valid:
            raise ValueError(f"ENVIRONMENT must be one of {valid}, got {v!r}")
        return lower


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.
    Cached so .env is only parsed once per process.
    """
    return Settings()


# Module-level convenience — import `settings` directly
settings = get_settings()

# Configure root logger once, here, so every module that does
# `logging.getLogger(__name__)` inherits the right level.
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)