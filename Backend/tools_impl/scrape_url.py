import logging
import time
import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from tools_impl.helpers import (
    _fetch_with_retry,
    _clean_html,
    _trim_to_sentence,
    _is_valid_url,
    MAX_SCRAPED_CHARS,
)
from tools_impl.extract_pdf import _extract_pdf_from_bytes

logger = logging.getLogger(__name__)


class ScrapeURLInput(BaseModel):
    url: str = Field(
        ...,
        description="The fully-qualified HTTP/HTTPS URL of the page to scrape.",
    )

    @field_validator("url")
    @classmethod
    def must_be_valid_url(cls, v: str) -> str:
        if not _is_valid_url(v):
            raise ValueError(f"Invalid URL: {v!r}")
        return v


@tool(args_schema=ScrapeURLInput)
def scrape_url(url: str) -> str:
    """
    Fetch and extract clean readable text from a web page.
    Strips navigation, ads, scripts, and boilerplate.
    Transparently handles pages that redirect to a PDF.
    Use after scholar_search or web_search to deep-read a specific paper page.
    """
    logger.info("scrape_url | url=%s", url)
    start = time.perf_counter()

    try:
        response = _fetch_with_retry(url)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "unknown"
        logger.warning("scrape_url HTTP error | url=%s | status=%s", url, status)
        return f"[HTTP_ERROR] Server returned status {status} for {url}."
    except (requests.ConnectionError, requests.Timeout) as exc:
        logger.warning("scrape_url network error | url=%s | %s", url, exc)
        return f"[NETWORK_ERROR] Could not reach {url} after retries: {exc}"
    except Exception as exc:
        logger.error("scrape_url unexpected | url=%s | %s", url, exc)
        return f"[SCRAPE_ERROR] Unexpected error scraping {url}: {exc}"

    content_type = response.headers.get("Content-Type", "")
    if "application/pdf" in content_type:
        logger.info("scrape_url detected PDF, delegating | url=%s", url)
        return _extract_pdf_from_bytes(response.content, source_url=url)

    text = _clean_html(response.text)
    if not text:
        return f"[EMPTY_CONTENT] No extractable text at {url}."

    trimmed = _trim_to_sentence(text, MAX_SCRAPED_CHARS)
    logger.info(
        "scrape_url complete | url=%s | chars=%d | elapsed=%.2fs",
        url, len(trimmed), time.perf_counter() - start,
    )
    return (
        f"SOURCE: {url}\n"
        f"EXTRACTED CONTENT ({len(trimmed)} chars):\n"
        f"{'=' * 60}\n"
        f"{trimmed}"
    )
