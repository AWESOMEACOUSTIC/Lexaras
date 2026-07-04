from __future__ import annotations
import logging
import time
import datetime
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from agents_impl.state import AgentState
from agents_impl.discovery import node_discovery
from agents_impl.extraction import node_extraction
from agents_impl.writer import node_writer
from agents_impl.evaluator import node_evaluator
from config import settings

logger = logging.getLogger(__name__)

MAX_DISCOVERY_RETRIES = 2
MIN_PAPERS_REQUIRED   = 3


def should_retry_discovery(state: AgentState) -> str:
    """
    Route: if we have enough papers → proceed to extraction.
    If not and retries remain → loop back to discovery with retry_count incremented
    so _generate_queries() knows to broaden the search.
    """
    papers  = state.get("discovered_papers", [])
    retries = state.get("retry_count", 0)

    if len(papers) >= MIN_PAPERS_REQUIRED:
        logger.info("[Router] %d papers — proceeding to extraction.", len(papers))
        return "proceed"

    if retries < MAX_DISCOVERY_RETRIES:
        logger.warning(
            "[Router] Only %d papers found. Retry %d/%d.",
            len(papers), retries + 1, MAX_DISCOVERY_RETRIES,
        )
        return "retry"

    logger.warning(
        "[Router] Max retries reached with %d papers. Proceeding anyway.", len(papers)
    )
    return "proceed"


def node_increment_retry(state: AgentState) -> AgentState:
    """Increment retry counter; reset paper lists so discovery runs fresh."""
    state["retry_count"]       = state.get("retry_count", 0) + 1
    state["scholar_papers"]    = []
    state["web_papers"]        = []
    state["discovered_papers"] = []
    return state


def build_pipeline() -> Any:
    """
    Compile the Lexaras LangGraph pipeline.

    Topology:
        discovery ──[enough papers?]──► extraction ──► writer ──► evaluator ──► END
                        │ no
                        ▼
                  increment_retry ──► discovery  (max MAX_DISCOVERY_RETRIES loops)
    """
    graph = StateGraph(AgentState)

    graph.add_node("discovery",       node_discovery)
    graph.add_node("increment_retry", node_increment_retry)
    graph.add_node("extraction",      node_extraction)
    graph.add_node("writer",          node_writer)
    graph.add_node("evaluator",       node_evaluator)

    graph.set_entry_point("discovery")

    graph.add_conditional_edges(
        "discovery",
        should_retry_discovery,
        {"retry": "increment_retry", "proceed": "extraction"},
    )
    graph.add_edge("increment_retry", "discovery")
    graph.add_edge("extraction",      "writer")
    graph.add_edge("writer",          "evaluator")
    graph.add_edge("evaluator",       END)

    return graph.compile()


# Singleton — compiled once at import time
pipeline = build_pipeline()


def run_research(
    topic:       str,
    search_mode: Literal["default", "scholar_only"] = "default",
) -> dict:
    """
    Run the full Lexaras research pipeline.

    Args:
        topic       : The research topic or question (non-empty string).
        search_mode : "default"      — up to ACADEMIC_QUOTA papers from Google Scholar,
                                       remainder from Tavily web search.
                      "scholar_only" — all papers from Google Scholar only,
                                       year-descending across SCHOLAR_YEARS years.

    Returns:
        Final AgentState dict. Key fields for the caller:
            draft_report       — full Markdown research report
            evaluation         — dict with scores and verdict
            discovered_papers  — list of PaperMeta dicts
            scholar_papers     — Scholar-only subset
            web_papers         — Tavily-only subset
            extraction_errors  — list of failed URLs
            error_log          — pipeline-level non-fatal errors
    """
    if not topic or not topic.strip():
        raise ValueError("Research topic must be a non-empty string.")

    valid_modes = {"default", "scholar_only"}
    if search_mode not in valid_modes:
        raise ValueError(
            f"search_mode must be one of {valid_modes}, got {search_mode!r}"
        )

    current_year = datetime.datetime.now().year
    year_from    = current_year - settings.SCHOLAR_YEARS
    year_to      = current_year

    logger.info(
        "=== Lexaras Pipeline | topic=%r | mode=%s | years=%d-%d ===",
        topic, search_mode, year_from, year_to,
    )
    overall_start = time.perf_counter()

    initial_state: AgentState = {
        "topic":             topic.strip(),
        "search_mode":       search_mode,
        "year_from":         year_from,
        "year_to":           year_to,
        "scholar_papers":    [],
        "web_papers":        [],
        "discovered_papers": [],
        "search_queries":    [],
        "discovery_raw":     "",
        "extracted_contexts": [],
        "extraction_errors": [],
        "draft_report":      "",
        "evaluation":        {},
        "retry_count":       0,
        "error_log":         [],
    }

    final_state = pipeline.invoke(initial_state)

    elapsed = time.perf_counter() - overall_start
    score   = final_state.get("evaluation", {}).get("overall_score", "N/A")

    logger.info(
        "=== Lexaras Complete | topic=%r | mode=%s | score=%s | elapsed=%.2fs ===",
        topic, search_mode, score, elapsed,
    )
    return final_state
