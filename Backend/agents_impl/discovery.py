import json
import logging
import time
import datetime
from langchain_core.messages import HumanMessage, SystemMessage

from agents_impl.state import AgentState
from agents_impl.llm import llm
from config import settings
from tools_impl.scholar_search import execute_scholar_search_raw
from tools_impl.web_search import execute_web_search_raw

logger = logging.getLogger(__name__)


def node_discovery(state: AgentState) -> AgentState:
    """
    Discovery node: Refactored to implement structured query generation and a
    deterministic year-descending search loop matching the search_mode.
    """
    topic = state["topic"]
    retries = state.get("retry_count", 0)
    logger.info("[Discovery] Starting | topic=%r | retry=%d", topic, retries)
    start = time.perf_counter()

    # Step 1: Generate distinct, complementary search queries using the LLM
    query_system = (
        "You are Lexaras Discovery — a specialised academic research intelligence agent.\n"
        "Your sole responsibility is to generate 2 to 4 distinct, complementary search queries that together "
        "cover the research topic from different angles (theoretical, empirical, recent advances, key authors).\n"
        "Do NOT include year constraints in the queries. Return ONLY a valid JSON object matching the schema:\n"
        "{\n"
        '    "search_queries": ["query 1", "query 2", ...]\n'
        "}\n"
        "No preamble, no markdown code fences, just plain JSON."
    )
    
    query_human = (
        f"Research Topic: {topic}\n"
        f"Previous retry count: {retries}\n\n"
        "Generate 2-4 search queries to find the most relevant papers. "
        "If retry count is > 0, make the queries broader to expand search coverage."
    )

    try:
        query_response = llm.invoke([
            SystemMessage(content=query_system),
            HumanMessage(content=query_human)
        ])
        raw_queries = query_response.content.strip()
        cleaned_queries = raw_queries.removeprefix("```json").removesuffix("```").strip()
        parsed_queries = json.loads(cleaned_queries)
        queries = parsed_queries.get("search_queries", [topic])
    except Exception as exc:
        logger.warning("[Discovery] Failed to generate structured queries, falling back to topic query: %s", exc)
        queries = [topic]

    state["search_queries"] = queries
    logger.info("[Discovery] Generated search queries: %r", queries)

    # Step 2: Set up loop parameters
    current_year = datetime.date.today().year
    search_mode = settings.SEARCH_MODE
    academic_quota = settings.ACADEMIC_QUOTA
    total_quota = settings.TOTAL_PAPER_QUOTA
    scholar_years = settings.SCHOLAR_YEARS

    collected_papers = []
    seen_urls = set()
    raw_logs = []

    # Step 3: Run search loop based on search_mode
    if search_mode == "scholar_only":
        logger.info("[Discovery] Running in scholar_only mode (quota: %d)", total_quota)
        # Year-descending Scholar-only loop
        for year in range(current_year, current_year - scholar_years - 1, -1):
            if len(collected_papers) >= total_quota:
                break
            for q in queries:
                if len(collected_papers) >= total_quota:
                    break
                logger.info("[Discovery] Scholar Search | Query: %r | Year: %d", q, year)
                try:
                    papers = execute_scholar_search_raw(
                        query=q,
                        year_from=year,
                        year_to=year,
                        max_results=5,
                    )
                    raw_logs.append(f"Scholar search for '{q}' in {year} found {len(papers)} papers.")
                    for p in papers:
                        url = p["url"]
                        norm_url = url.strip().rstrip("/").lower()
                        if norm_url not in seen_urls:
                            seen_urls.add(norm_url)
                            collected_papers.append(p)
                            if len(collected_papers) >= total_quota:
                                break
                except Exception as e:
                    err_msg = f"Scholar search failed for query '{q}' in {year}: {e}"
                    logger.warning("[Discovery] %s", err_msg)
                    state["error_log"] = state.get("error_log", []) + [err_msg]

    else:
        # Default mode: collect academic_quota from Google Scholar first, then fill remainder with web search
        logger.info(
            "[Discovery] Running in default mode (scholar quota: %d, total quota: %d)",
            academic_quota, total_quota,
        )
        # Academic portion
        for year in range(current_year, current_year - scholar_years - 1, -1):
            if len(collected_papers) >= academic_quota:
                break
            for q in queries:
                if len(collected_papers) >= academic_quota:
                    break
                logger.info("[Discovery] Scholar Search | Query: %r | Year: %d", q, year)
                try:
                    papers = execute_scholar_search_raw(
                        query=q,
                        year_from=year,
                        year_to=year,
                        max_results=5,
                    )
                    raw_logs.append(f"Scholar search for '{q}' in {year} found {len(papers)} papers.")
                    for p in papers:
                        url = p["url"]
                        norm_url = url.strip().rstrip("/").lower()
                        if norm_url not in seen_urls:
                            seen_urls.add(norm_url)
                            collected_papers.append(p)
                            if len(collected_papers) >= academic_quota:
                                break
                except Exception as e:
                    err_msg = f"Scholar search failed for query '{q}' in {year}: {e}"
                    logger.warning("[Discovery] %s", err_msg)
                    state["error_log"] = state.get("error_log", []) + [err_msg]

        # Web fill portion
        remainder_quota = total_quota - len(collected_papers)
        if remainder_quota > 0:
            logger.info("[Discovery] Filling remaining %d slot(s) with Web Search", remainder_quota)
            for q in queries:
                if len(collected_papers) >= total_quota:
                    break
                logger.info("[Discovery] Web Search | Query: %r", q)
                try:
                    results = execute_web_search_raw(query=q, max_results=5)
                    raw_logs.append(f"Web search for '{q}' found {len(results)} results.")
                    for p in results:
                        url = p["url"]
                        norm_url = url.strip().rstrip("/").lower()
                        if norm_url not in seen_urls:
                            seen_urls.add(norm_url)
                            collected_papers.append(p)
                            if len(collected_papers) >= total_quota:
                                break
                except Exception as e:
                    err_msg = f"Web search failed for query '{q}': {e}"
                    logger.warning("[Discovery] %s", err_msg)
                    state["error_log"] = state.get("error_log", []) + [err_msg]

    state["discovery_raw"] = "\n".join(raw_logs)

    # Step 4: Call LLM to generate one-sentence relevance notes for the final selected papers
    if not collected_papers:
        logger.warning("[Discovery] No papers collected.")
        state["discovered_papers"] = []
        return state

    papers_summary_parts = []
    for i, p in enumerate(collected_papers, start=1):
        summary_part = (
            f"Paper [{i}]:\n"
            f"  Title: {p['title']}\n"
            f"  URL: {p['url']}\n"
            f"  Snippet: {p['snippet']}\n"
        )
        papers_summary_parts.append(summary_part)
    papers_block = "\n".join(papers_summary_parts)

    relevance_system = (
        "You are Lexaras Discovery — a specialised academic research intelligence agent.\n"
        "Your job is to read the research topic and the list of candidate papers, and write a "
        "one-sentence relevance note for each paper explaining why it matters for this topic.\n"
        "Return ONLY a valid JSON object matching the schema:\n"
        "{\n"
        '    "relevance_notes": [\n'
        '        {"url": "...", "relevance_note": "..."},\n'
        "        ...\n"
        "    ]\n"
        "}\n"
        "No preamble, no markdown formatting."
    )

    relevance_human = (
        f"Research Topic: {topic}\n\n"
        "Candidate Papers:\n"
        f"{papers_block}\n\n"
        "Generate a one-sentence relevance note for each paper."
    )

    notes_by_url = {}
    try:
        relevance_response = llm.invoke([
            SystemMessage(content=relevance_system),
            HumanMessage(content=relevance_human)
        ])
        raw_notes = relevance_response.content.strip()
        cleaned_notes = raw_notes.removeprefix("```json").removesuffix("```").strip()
        parsed_notes = json.loads(cleaned_notes)
        for entry in parsed_notes.get("relevance_notes", []):
            url_key = entry.get("url", "").strip().rstrip("/").lower()
            if url_key:
                notes_by_url[url_key] = entry.get("relevance_note", "")
    except Exception as exc:
        logger.warning("[Discovery] Failed to generate relevance notes: %s", exc)

    final_papers = []
    for p in collected_papers:
        url_key = p["url"].strip().rstrip("/").lower()
        fallback_note = f"Relevant academic reference discussing fields related to the topic: {topic}."
        final_papers.append({
            "title": p["title"],
            "url": p["url"],
            "snippet": p["snippet"],
            "relevance_note": notes_by_url.get(url_key) or fallback_note,
            "publication_year": p["publication_year"],
            "authors": p["authors"],
            "citation_count": p["citation_count"],
        })

    state["discovered_papers"] = final_papers
    logger.info(
        "[Discovery] Complete | papers_found=%d | elapsed=%.2fs",
        len(final_papers),
        time.perf_counter() - start,
    )
    return state
