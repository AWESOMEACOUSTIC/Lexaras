import logging
import time
import textwrap
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from config import settings
from tools_impl.helpers import (
    _trim_to_sentence,
    SEARCH_MAX_RESULTS,
    MAX_SNIPPET_CHARS,
)

logger = logging.getLogger(__name__)

_tavily = TavilyClient(api_key=settings.TAVILY_API_KEY)

class WebSearchInput(BaseModel):
    query: str = Field(
        ...,
        description=(
            "A precise, self-contained search query for finding academic papers, "
            "research articles, or technical information. Include specific terminology, "
            "author names, or publication years when known."
        ),
        min_length=3,
        max_length=300,
    )
    max_results: int = Field(
        default=SEARCH_MAX_RESULTS,
        ge=1,
        le=10,
        description="Number of search results to retrieve.",
    )

@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = SEARCH_MAX_RESULTS) -> str:
    """
    Search the web using Tavily and return structured results including
    titles, source URLs, publication dates (when available), and content snippets.
    Prioritises academic and research sources.
    Use this tool to discover relevant research papers and authoritative references
    for a given topic.
    """
    logger.info("web_search called | query=%r | max_results=%d", query, max_results)
    start = time.perf_counter()

    try:
        response = _tavily.search(
            query=query,
            max_results=max_results,
            include_raw_content=False,   # we scrape ourselves for deeper reads
            include_answer=False,
            search_depth="advanced",     # uses Tavily's smarter ranking
        )
    except Exception as exc:
        logger.error("Tavily search failed | query=%r | error=%s", query, exc)
        return f"[SEARCH_ERROR] Could not complete search for '{query}': {exc}"

    results = response.get("results", [])
    if not results:
        logger.warning("web_search returned 0 results | query=%r", query)
        return f"[NO_RESULTS] No results found for query: '{query}'. Try rephrasing or broadening the search."

    lines: list[str] = [
        f"SEARCH RESULTS FOR: {query!r}",
        f"Retrieved {len(results)} result(s) in {time.perf_counter() - start:.2f}s",
        "=" * 60,
    ]

    for i, r in enumerate(results, start=1):
        snippet = _trim_to_sentence(r.get("content", ""), MAX_SNIPPET_CHARS)
        published = r.get("published_date", "Unknown date")
        lines.append(
            textwrap.dedent(f"""
            [{i}] {r.get('title', 'Untitled')}
                URL      : {r.get('url', 'N/A')}
                Published: {published}
                Snippet  : {snippet}
            """).strip()
        )
        lines.append("-" * 60)

    logger.info("web_search completed | query=%r | results=%d", query, len(results))
    return "\n".join(lines)
