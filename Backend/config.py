"""
config.py — Lexaras Research Platform
---------------------------------------
Centralised application configuration using Pydantic BaseSettings.

All secrets validated at startup — a missing key is a startup crash,
not a silent None that surfaces 45 seconds into a pipeline run.

New in this version:
    - SERPAPI_API_KEY  : required for Google Scholar search
    - SEARCH_MODE      : "default" | "scholar_only"
    - SCHOLAR_YEARS    : how many years back to search (default 5)
    - ACADEMIC_QUOTA   : how many of the total results must come from
                         Google Scholar in default mode (default 5)
    - TOTAL_PAPER_QUOTA: total papers to collect across all sources (default 10)
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM Providers ────────────────────────────────────────────────────────
    MISTRAL_API_KEY: str = Field(..., description="Mistral AI API key")
    GROQ_API_KEY: str | None = Field(None, description="Groq API key (fallback LLM)")

    # ── Tool Providers ────────────────────────────────────────────────────────
    TAVILY_API_KEY: str = Field(..., description="Tavily search API key")
    SERPAPI_API_KEY: str = Field(..., description="SerpApi key — required for Google Scholar search")

    # ── Search behaviour ─────────────────────────────────────────────────────
    # "default"      → ACADEMIC_QUOTA papers from Scholar + remainder from Tavily
    # "scholar_only" → all papers from Google Scholar, year-windowed
    SEARCH_MODE: Literal["default", "scholar_only"] = Field(
        "default",
        description="Search mode: 'default' (mixed) or 'scholar_only' (Google Scholar only)",
    )
    SCHOLAR_YEARS: int = Field(
        5,
        ge=1,
        le=20,
        description="How many years back from the current year Scholar search spans",
    )
    ACADEMIC_QUOTA: int = Field(
        5,
        ge=1,
        le=10,
        description="In default mode: minimum papers that must come from Google Scholar",
    )
    TOTAL_PAPER_QUOTA: int = Field(
        10,
        ge=3,
        le=20,
        description="Total papers to collect across all sources",
    )

    # ── Observability ─────────────────────────────────────────────────────────
    LANGCHAIN_API_KEY: str | None = Field(None, description="LangSmith tracing key")
    LANGCHAIN_TRACING_V2: bool = Field(False, description="Enable LangSmith tracing")
    LANGCHAIN_PROJECT: str = Field("lexaras", description="LangSmith project name")

    # ── Application ───────────────────────────────────────────────────────────
    LOG_LEVEL: str = Field("INFO", description="Python logging level")
    ENVIRONMENT: str = Field(
        "development",
        description="deployment environment: development | staging | production",
    )

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("MISTRAL_API_KEY", "TAVILY_API_KEY", "SERPAPI_API_KEY")
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
    """Singleton — .env is parsed exactly once per process lifetime."""
    return Settings()


settings = get_settings()

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)