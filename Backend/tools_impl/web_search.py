import logging
import re
import time
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from config import settings
from tools_impl.helpers import (
    _trim_to_sentence,
    _result_envelope,
    MAX_SNIPPET_CHARS,
    WEB_MAX_RESULTS,
)

logger = logging.getLogger(__name__)

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)

class WebSearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "A precise, self-contained search query for finding academic papers, "
            "research articles, or technical content. Include specific terminology, "
            "author names, or publication years when known."
        ),
        min_length=3,
        max_length=300,
    )
    max_results: int = Field(
        default=WEB_MAX_RESULTS,
        ge=1,
        le=10,
        description="Number of web results to retrieve.",
    )


def execute_web_search_raw(query: str, max_results: int = WEB_MAX_RESULTS) -> list[dict]:
    """
    Lower-level Python helper for executing Tavily web searches and normalizing results.
    Returns list of dicts: {title, url, snippet, source, publication_year, authors, citation_count}
    """
    logger.info("execute_web_search_raw | query=%r | max_results=%d", query, max_results)
    try:
        response = _tavily.search(
            query=query,
            max_results=max_results,
            include_raw_content=False,
            include_answer=False,
            search_depth="advanced",
        )
    except Exception as exc:
        logger.error("web_search Tavily error | query=%r | %s", query, exc)
        raise exc

    results = response.get("results", [])
    parsed: list[dict] = []
    
    for r in results:
        # Attempt to extract a year from published_date if present
        pub_date  = r.get("published_date", "")
        pub_year  = None
        if pub_date:
            m = re.search(r"\b(20\d{2}|19\d{2})\b", pub_date)
            if m:
                pub_year = int(m.group(1))
                
        parsed.append({
            "title": r.get("title", "Untitled"),
            "url": r.get("url", "N/A"),
            "snippet": _trim_to_sentence(r.get("content", ""), MAX_SNIPPET_CHARS),
            "source": "web",
            "publication_year": pub_year,
            "authors": None,
            "citation_count": None,
        })
    return parsed


@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = WEB_MAX_RESULTS) -> str:
    """
    Search the open web using Tavily.
    Returns titles, URLs, publication dates, and content snippets from
    blogs, preprint servers, news outlets, and non-paywalled pages.
    Use this to supplement Google Scholar results with broader web sources.
    Do NOT use this when search_mode is 'scholar_only'.
    """
    logger.info("web_search tool | query=%r | max_results=%d", query, max_results)
    start = time.perf_counter()
    
    try:
        papers = execute_web_search_raw(query=query, max_results=max_results)
    except Exception as exc:
        return f"[SEARCH_ERROR] Tavily search failed for '{query}': {exc}"

    if not papers:
        logger.warning("web_search no results | query=%r", query)
        return (
            f"[NO_RESULTS] No web results for '{query}'. "
            "Try rephrasing or broadening the query."
        )

    lines = [
        f"WEB SEARCH RESULTS FOR: {query!r}",
        f"Retrieved {len(papers)} result(s) in {time.perf_counter() - start:.2f}s",
        "=" * 60,
    ]
    for i, p in enumerate(papers, start=1):
        lines.append(
            _result_envelope(
                index=i,
                title=p["title"],
                url=p["url"],
                snippet=p["snippet"],
                source="web",
                publication_year=p["publication_year"],
            )
        )
        lines.append("-" * 60)

    logger.info("web_search complete | query=%r | results=%d", query, len(papers))
    return "\n".join(lines)
