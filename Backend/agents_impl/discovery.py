import json
import logging
import textwrap
import time
from typing import Optional

from langchain_core.messages import HumanMessage
from agents_impl.state import AgentState, PaperMeta
from agents_impl.llm import llm
from config import settings
from tools import (
    scholar_search,
    web_search,
)
from tools_impl.domain_reputation import get_reputation, is_domain_blocked

logger = logging.getLogger(__name__)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that Mistral sometimes wraps JSON in."""
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


def _deduplicate_papers(papers: list[PaperMeta]) -> list[PaperMeta]:
    """
    Remove duplicates by URL, preserving insertion order.
    Scholar result takes precedence over web result if the same URL appears in both.
    """
    seen: set[str] = set()
    out:  list[PaperMeta] = []
    for p in papers:
        url = p.get("url", "").strip().rstrip("/")
        if url and url not in seen:
            seen.add(url)
            out.append(p)
    return out


def _sort_by_year(papers: list[PaperMeta]) -> list[PaperMeta]:
    """
    Sort papers newest-first. Papers with no publication_year sink to the bottom
    rather than crashing the sort.
    """
    return sorted(
        papers,
        key=lambda p: p.get("publication_year") or 0,
        reverse=True,
    )


def _rank_by_domain_reputation(papers: list[PaperMeta]) -> list[PaperMeta]:
    """
    Reorders a batch of candidate papers so higher-reputation domains (per
    tools_impl/domain_reputation.py's recorded extraction success rate) sort
    first, and drops chronic-offender domains outright. This is a soft
    re-ranking, not a hard cutoff for most domains — a domain we've barely
    seen gets the neutral default score rather than being punished, so a
    genuinely good but rarely-used source isn't unfairly buried.

    Only applied to web-sourced candidates: Scholar/SerpApi results are
    already high-quality by construction (prefer direct PDF links — see
    scholar_search.py), so this feedback loop matters most for the more
    variable Tavily web fill.
    """
    survivors = [p for p in papers if not is_domain_blocked(p.get("url", ""))]
    dropped = len(papers) - len(survivors)
    if dropped:
        logger.info(
            "[Discovery] Domain-reputation hard filter dropped %d chronic-offender result(s)",
            dropped,
        )
    return sorted(survivors, key=lambda p: get_reputation(p.get("url", "")), reverse=True)


def _parse_tool_output_to_papers(
    raw_output: str,
    source: str,
) -> list[PaperMeta]:
    """
    Parse the structured text envelope that web_search and scholar_search return
    into a list of PaperMeta dicts.
    """
    import re

    papers: list[PaperMeta] = []
    blocks = re.split(r"\n-{20,}\n", raw_output)

    for block in blocks:
        block = block.strip()
        if not block or block.startswith("GOOGLE SCHOLAR") or block.startswith("WEB SEARCH"):
            continue

        title_match = re.search(r"^\[?\d+\]?\s*(.+)$", block, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Untitled"

        url_match = re.search(r"URL\s*:\s*(\S+)", block)
        url = url_match.group(1).strip() if url_match else ""

        year_match = re.search(r"Year\s*:\s*(\d{4})", block)
        pub_year = int(year_match.group(1)) if year_match else None

        authors_match = re.search(r"Authors\s*:\s*(.+)$", block, re.MULTILINE)
        authors = authors_match.group(1).strip() if authors_match else None
        if authors and authors.lower() in ("unknown", "n/a", ""):
            authors = None

        snippet_match = re.search(r"Snippet\s*:\s*(.+?)(?=\n\S|\Z)", block, re.DOTALL)
        snippet = snippet_match.group(1).strip() if snippet_match else ""

        if not url:
            continue

        papers.append(PaperMeta(
            title=title,
            url=url,
            snippet=snippet,
            relevance_note="",
            source=source,
            publication_year=pub_year,
            authors=authors,
        ))

    return papers


def _score_relevance_notes(
    papers: list[PaperMeta],
    topic: str,
) -> list[PaperMeta]:
    """
    Ask the LLM to write a one-sentence relevance_note for each paper.
    Batched into a single call to keep token usage minimal.
    """
    if not papers:
        return papers

    paper_list = "\n".join(
        f"{i}. Title: {p['title']}\n   Snippet: {p['snippet'][:200]}"
        for i, p in enumerate(papers, 1)
    )

    prompt = textwrap.dedent(f"""
        Research topic: {topic}

        For each paper below, write a single sentence explaining why it is or is not
        relevant to the research topic. Be specific. If it is not relevant, say so.

        Papers:
        {paper_list}

        Respond ONLY with valid JSON — a list of objects in the same order:
        [
            {{"index": 1, "relevance_note": "..."}},
            {{"index": 2, "relevance_note": "..."}}
        ]
    """).strip()

    try:
        raw = llm.invoke([HumanMessage(content=prompt)]).content
        notes: list[dict] = json.loads(_strip_fences(raw))
        note_map = {item["index"]: item["relevance_note"] for item in notes}
        for i, p in enumerate(papers, 1):
            p["relevance_note"] = note_map.get(i, "Relevance assessment unavailable.")
    except Exception as exc:
        logger.warning("[Discovery] relevance scoring failed: %s", exc)
        for p in papers:
            if not p.get("relevance_note"):
                p["relevance_note"] = "Relevance assessment unavailable."

    return papers


# ── QUERY GENERATION ──────────────────────────────────────────────────────────

_QUERY_GEN_PROMPT = textwrap.dedent("""
    You are a senior research librarian generating precise academic search queries.

    Research topic: {topic}
    Search mode: {search_mode}
    Retry attempt: {retry_count} (0 = first attempt)

    Generate {num_queries} distinct search queries that together cover the topic from
    complementary angles:
        - Core terminology / primary concept
        - Empirical studies / experimental results
        - Recent advances / state of the art (use terms like "2023 2024 2025")
        - Key authors or landmark papers (if you know them)

    If retry_count > 0, the previous queries returned too few results.
    Broaden the queries: use synonyms, parent concepts, or adjacent fields.

    Respond ONLY with valid JSON — a flat list of strings:
    ["query one", "query two", "query three"]
""").strip()


def _generate_queries(topic: str, search_mode: str, retry_count: int) -> list[str]:
    """
    Ask the LLM to generate 2-4 diverse search queries for the topic.
    Returns a list of query strings.
    """
    num_queries = 3 if retry_count == 0 else 4

    prompt = _QUERY_GEN_PROMPT.format(
        topic=topic,
        search_mode=search_mode,
        retry_count=retry_count,
        num_queries=num_queries,
    )
    try:
        raw    = llm.invoke([HumanMessage(content=prompt)]).content
        queries: list[str] = json.loads(_strip_fences(raw))
        if not isinstance(queries, list) or not queries:
            raise ValueError("LLM returned empty or non-list queries")
        return [str(q).strip() for q in queries if str(q).strip()]
    except Exception as exc:
        logger.warning("[Discovery] query generation failed (%s), using topic as fallback", exc)
        return [topic]


# ── COLLECTION LOOPS ─────────────────────────────────────────────────────────

def _collect_scholar_papers(
    queries: list[str],
    year_from: int,
    year_to: int,
    quota: int,
) -> tuple[list[PaperMeta], list[str], str]:
    """
    Year-descending Scholar collection loop.
    """
    papers:       list[PaperMeta] = []
    queries_fired: list[str]      = []
    raw_parts:    list[str]       = []

    for query in queries:
        if len(papers) >= quota:
            break

        for year in range(year_to, year_from - 1, -1):
            remaining = quota - len(papers)
            if remaining <= 0:
                break

            queries_fired.append(f"{query} [{year}]")
            logger.info(
                "[Discovery] Scholar search | query=%r | year=%d | need=%d",
                query, year, remaining,
            )

            try:
                raw = scholar_search.invoke({
                    "query":       query,
                    "year_from":   year,
                    "year_to":     year,
                    "max_results": min(remaining + 2, 10),
                })
                raw_parts.append(raw)

                if any(tag in raw for tag in (
                    "[SCHOLAR_ERROR]", "[NO_SCHOLAR_RESULTS]",
                    "[SCHOLAR_HTTP_ERROR]", "[SCHOLAR_QUOTA_EXCEEDED]",
                    "[SCHOLAR_NETWORK_ERROR]", "[NO_USABLE_SCHOLAR_RESULTS]",
                )):
                    logger.warning(
                        "[Discovery] Scholar returned error for query=%r year=%d",
                        query, year,
                    )
                    continue

                batch = _parse_tool_output_to_papers(raw, source="scholar")
                papers.extend(batch)
                logger.info(
                    "[Discovery] Scholar window done | year=%d | batch=%d | total=%d",
                    year, len(batch), len(papers),
                )

            except Exception as exc:
                logger.error(
                    "[Discovery] Scholar call failed | query=%r | year=%d | %s",
                    query, year, exc,
                )

    return papers, queries_fired, "\n\n".join(raw_parts)


def _collect_web_papers(
    queries: list[str],
    quota: int,
) -> tuple[list[PaperMeta], list[str], str]:
    """
    Tavily web search fill — runs until quota is met or all queries exhausted.

    Each batch is passed through the domain-reputation cache before being
    added to the running total: chronic-offender domains (many recorded
    extraction failures) are dropped outright, and the remainder is sorted
    so historically-reliable domains are preferred when later batches get
    trimmed to the remaining quota. See tools_impl/domain_reputation.py.
    """
    papers:        list[PaperMeta] = []
    queries_fired: list[str]       = []
    raw_parts:     list[str]       = []

    for query in queries:
        if len(papers) >= quota:
            break

        remaining = quota - len(papers)
        queries_fired.append(query)
        logger.info(
            "[Discovery] Web search | query=%r | need=%d", query, remaining,
        )

        try:
            raw = web_search.invoke({
                "query":       query,
                "max_results": min(remaining + 2, 10),
            })
            raw_parts.append(raw)

            if any(tag in raw for tag in ("[SEARCH_ERROR]", "[NO_RESULTS]")):
                logger.warning("[Discovery] Web search returned error for query=%r", query)
                continue

            batch = _parse_tool_output_to_papers(raw, source="web")
            batch = _rank_by_domain_reputation(batch)
            papers.extend(batch)
            logger.info(
                "[Discovery] Web batch done | query=%r | batch=%d | total=%d",
                query, len(batch), len(papers),
            )

        except Exception as exc:
            logger.error("[Discovery] Web call failed | query=%r | %s", query, exc)

    return papers, queries_fired, "\n\n".join(raw_parts)


# ── NODE ENTRY ────────────────────────────────────────────────────────────────

def node_discovery(state: AgentState) -> AgentState:
    """
    Discovery node — orchestrates the full paper collection strategy.
    """
    topic       = state["topic"]
    mode        = state["search_mode"]
    year_from   = state["year_from"]
    year_to     = state["year_to"]
    retry_count = state.get("retry_count", 0)

    academic_quota = settings.ACADEMIC_QUOTA
    total_quota    = settings.TOTAL_PAPER_QUOTA

    logger.info(
        "[Discovery] Starting | topic=%r | mode=%s | years=%d-%d | retry=%d",
        topic, mode, year_from, year_to, retry_count,
    )
    start = time.perf_counter()

    all_queries:   list[str] = []
    all_raw_parts: list[str] = []

    # 1. Generate queries
    queries = _generate_queries(topic, mode, retry_count)
    all_queries.extend(queries)
    logger.info("[Discovery] Generated %d queries: %s", len(queries), queries)

    # 2. Google Scholar — year-descending
    scholar_quota = total_quota if mode == "scholar_only" else academic_quota

    scholar_papers_raw, sq_fired, scholar_raw = _collect_scholar_papers(
        queries=queries,
        year_from=year_from,
        year_to=year_to,
        quota=scholar_quota,
    )
    all_queries.extend(sq_fired)
    all_raw_parts.append(scholar_raw)

    scholar_papers = _sort_by_year(_deduplicate_papers(scholar_papers_raw))
    logger.info(
        "[Discovery] Scholar collection done | unique=%d | quota=%d",
        len(scholar_papers), scholar_quota,
    )

    # 3. Tavily web fill (default mode only)
    web_papers: list[PaperMeta] = []
    if mode == "default":
        web_quota = total_quota - len(scholar_papers)
        if web_quota > 0:
            web_papers_raw, wq_fired, web_raw = _collect_web_papers(
                queries=queries,
                quota=web_quota,
            )
            all_queries.extend(wq_fired)
            all_raw_parts.append(web_raw)
            web_papers = _deduplicate_papers(web_papers_raw)
            logger.info(
                "[Discovery] Web fill done | unique=%d | quota=%d",
                len(web_papers), web_quota,
            )
        else:
            logger.info("[Discovery] Scholar quota met — skipping web fill.")

    # 4. Combine, deduplicate, sort
    combined = _deduplicate_papers(scholar_papers + web_papers)
    combined = _sort_by_year(combined)
    logger.info(
        "[Discovery] Combined pool | scholar=%d | web=%d | total=%d",
        len(scholar_papers), len(web_papers), len(combined),
    )

    # 5. LLM relevance scoring (batched)
    combined = _score_relevance_notes(combined, topic)

    # 6. Write to state
    state["scholar_papers"]    = scholar_papers
    state["web_papers"]        = web_papers
    state["discovered_papers"] = combined
    state["search_queries"]    = list(dict.fromkeys(all_queries))
    state["discovery_raw"]     = "\n\n".join(all_raw_parts)

    logger.info(
        "[Discovery] Complete | papers=%d | elapsed=%.2fs",
        len(combined), time.perf_counter() - start,
    )
    return state