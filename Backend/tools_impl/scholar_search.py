import logging
import re
import time
from typing import Optional

import serpapi
import requests
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from config import settings
from tools_impl.helpers import (
    _trim_to_sentence,
    _result_envelope,
    _is_valid_url,
    MAX_SNIPPET_CHARS,
)

logger = logging.getLogger(__name__)

# ── SerpApi client (official Python library) ───────────────────────────────────
_serpapi_client = serpapi.Client(api_key=settings.SERPAPI_API_KEY)


def _call_serpapi(params: dict) -> dict:
    """
    Call SerpApi using the official Python client.
    Isolated so Tenacity can wrap just this call for network-level retries.
    """
    return _serpapi_client.search(params)


_serpapi_retry = retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
_call_serpapi = _serpapi_retry(_call_serpapi)


def _parse_scholar_results(
    raw_results: list[dict],
    max_results: int,
) -> list[dict]:
    """
    Normalise SerpApi's organic_results into our standard paper dict shape.
    Each dict has: title, url, snippet, source, publication_year,
    authors, citation_count — the same keys _result_envelope expects.
    """
    seen_urls: set[str] = set()
    parsed: list[dict] = []

    for r in raw_results:
        url = r.get("link", "")
        if not url or not _is_valid_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title   = r.get("title", "Untitled")
        snippet = _trim_to_sentence(r.get("snippet", ""), MAX_SNIPPET_CHARS)

        pub_info   = r.get("publication_info", {})
        pub_summary = pub_info.get("summary", "")

        # Extract year from summary string
        year_match = re.search(r"\b(20\d{2}|19\d{2})\b", pub_summary)
        pub_year   = int(year_match.group(1)) if year_match else None

        # Extract authors — everything before the first " - "
        authors = None
        if " - " in pub_summary:
            authors = pub_summary.split(" - ")[0].strip()

        # Citation count lives in inline_links.cited_by.total
        cited_by       = r.get("inline_links", {}).get("cited_by", {})
        citation_count = cited_by.get("total", None)

        # PDF link if SerpApi found one
        resources = r.get("resources", [])
        pdf_url   = None
        for res in resources:
            if res.get("file_format", "").upper() == "PDF":
                pdf_url = res.get("link")
                break

        parsed.append({
            "title":          title,
            "url":            pdf_url or url,   # prefer direct PDF when available
            "landing_url":    url,              # always keep the Scholar landing page
            "snippet":        snippet,
            "source":         "scholar",
            "publication_year": pub_year,
            "authors":        authors,
            "citation_count": citation_count,
        })

        if len(parsed) >= max_results:
            break

    return parsed


class ScholarSearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "Academic search query for Google Scholar. Use precise terminology, "
            "field-specific language, and include author names or key terms "
            "when known. Do NOT include year constraints — those are handled "
            "by year_from and year_to."
        ),
        min_length=3,
        max_length=300,
    )
    year_from: int = Field(
        ...,
        ge=1990,
        le=2100,
        description=(
            "Start year of the publication window (inclusive). "
            "Set equal to year_to for a single-year window."
        ),
    )
    year_to: int = Field(
        ...,
        ge=1990,
        le=2100,
        description=(
            "End year of the publication window (inclusive). "
            "Must be >= year_from."
        ),
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of Scholar results to return for this window.",
    )

    @field_validator("year_to")
    @classmethod
    def year_to_gte_year_from(cls, v: int, info) -> int:
        year_from = info.data.get("year_from")
        if year_from is not None and v < year_from:
            raise ValueError(
                f"year_to ({v}) must be >= year_from ({year_from})"
            )
        return v


def execute_scholar_search_raw(
    query: str,
    year_from: int,
    year_to: int,
    max_results: int = 5,
) -> list[dict]:
    """
    Lower-level Python helper for executing SerpApi Scholar search and normalizing results.
    Returns list of dicts.
    """
    logger.info(
        "execute_scholar_search_raw | query=%r | years=%d-%d | max=%d",
        query, year_from, year_to, max_results,
    )
    
    params = {
        "engine":   "google_scholar",
        "q":        query,
        "num":      min(max_results * 2, 20),  # fetch extra; we filter and deduplicate
        "as_ylo":   year_from,
        "as_yhi":   year_to,
        "hl":       "en",
        "scisbd":   1,                         # sort by date (1=recent first)
    }

    try:
        data = _call_serpapi(params)
    except Exception as exc:
        logger.error("scholar_search error | query=%r | %s", query, exc)
        err_msg = str(exc).lower()
        if "rate" in err_msg or "429" in err_msg:
            raise RuntimeError("SerpApi rate limit reached (HTTP 429).")
        raise RuntimeError(f"SerpApi search failed: {exc}")

    if "error" in data:
        logger.error("scholar_search SerpApi error | %s", data["error"])
        raise RuntimeError(f"SerpApi error: {data['error']}")

    raw_results = data.get("organic_results", [])
    if not raw_results:
        return []

    return _parse_scholar_results(raw_results, max_results)


@tool(args_schema=ScholarSearchInput)
def scholar_search(
    query: str,
    year_from: int,
    year_to: int,
    max_results: int = 5,
) -> str:
    """
    Search Google Scholar via SerpApi and return structured academic paper results.
    Results are filtered to the year window [year_from, year_to] and include
    title, URL, authors, publication year, citation count, and abstract snippet.

    Always pass a narrow year window (ideally a single year) so results are
    temporally precise. The discovery node calls this tool multiple times in a
    year-descending loop to build up the full paper list from newest to oldest.

    Use this tool for all academic / peer-reviewed sources.
    """
    logger.info(
        "scholar_search tool | query=%r | years=%d-%d | max=%d",
        query, year_from, year_to, max_results,
    )
    start = time.perf_counter()

    try:
        papers = execute_scholar_search_raw(
            query=query,
            year_from=year_from,
            year_to=year_to,
            max_results=max_results,
        )
    except Exception as exc:
        return f"[SCHOLAR_ERROR] Scholar search failed: {exc}"

    if not papers:
        logger.warning(
            "scholar_search no results | query=%r | window=%d-%d",
            query, year_from, year_to,
        )
        return (
            f"[NO_SCHOLAR_RESULTS] No Google Scholar results for '{query}' "
            f"in the window {year_from}–{year_to}. "
            "Try broadening the query or extending the year range."
        )

    elapsed = time.perf_counter() - start
    lines   = [
        f"GOOGLE SCHOLAR RESULTS FOR: {query!r}  [{year_from}–{year_to}]",
        f"Retrieved {len(papers)} paper(s) in {elapsed:.2f}s",
        "=" * 60,
    ]
    for i, p in enumerate(papers, start=1):
        lines.append(
            _result_envelope(
                index=i,
                title=p["title"],
                url=p["url"],
                snippet=p["snippet"],
                source="scholar",
                publication_year=p["publication_year"],
                authors=p["authors"],
                citation_count=p["citation_count"],
            )
        )
        lines.append("-" * 60)

    logger.info(
        "scholar_search complete | query=%r | window=%d-%d | papers=%d",
        query, year_from, year_to, len(papers),
    )
    return "\n".join(lines)
