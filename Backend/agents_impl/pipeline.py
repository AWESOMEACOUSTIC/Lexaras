from __future__ import annotations
import logging
import time
from typing import Any

from langgraph.graph import END, StateGraph

from agents_impl.state import AgentState
from agents_impl.discovery import node_discovery
from agents_impl.extraction import node_extraction
from agents_impl.writer import node_writer
from agents_impl.evaluator import node_evaluator

logger = logging.getLogger(__name__)

MAX_DISCOVERY_RETRIES = 2


def should_retry_discovery(state: AgentState) -> str:
    """
    After discovery, check if we have enough papers to proceed.
    If not, and we haven't hit the retry cap, loop back to discovery
    with a modified approach (the retry count signals the agent to
    broaden its search).
    """
    papers = state.get("discovered_papers", [])
    retries = state.get("retry_count", 0)

    if len(papers) >= 3:
        logger.info("[Router] Sufficient papers found (%d). Proceeding to extraction.", len(papers))
        return "proceed"

    if retries < MAX_DISCOVERY_RETRIES:
        logger.warning(
            "[Router] Insufficient papers (%d). Retry %d/%d.",
            len(papers), retries + 1, MAX_DISCOVERY_RETRIES,
        )
        return "retry"

    logger.warning("[Router] Max retries reached with %d papers. Proceeding anyway.", len(papers))
    return "proceed"


def node_increment_retry(state: AgentState) -> AgentState:
    """Increments retry counter before looping back to discovery."""
    state["retry_count"] = state.get("retry_count", 0) + 1
    # Signal to the discovery agent to broaden its approach
    state["topic"] = state["topic"]  # topic unchanged but retry_count is visible
    return state



def build_pipeline() -> Any:
    """
    Assembles and compiles the Lexaras LangGraph pipeline.

    Graph topology:
        discovery → [retry? → increment → discovery] → extraction → writer → evaluator → END
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("discovery", node_discovery)
    graph.add_node("increment_retry", node_increment_retry)
    graph.add_node("extraction", node_extraction)
    graph.add_node("writer", node_writer)
    graph.add_node("evaluator", node_evaluator)

    # Entry point
    graph.set_entry_point("discovery")

    # Conditional retry edge after discovery
    graph.add_conditional_edges(
        "discovery",
        should_retry_discovery,
        {
            "retry": "increment_retry",
            "proceed": "extraction",
        },
    )

    # Retry loop back to discovery
    graph.add_edge("increment_retry", "discovery")

    # Linear path through the rest of the pipeline
    graph.add_edge("extraction", "writer")
    graph.add_edge("writer", "evaluator")
    graph.add_edge("evaluator", END)

    return graph.compile()


# Singleton compiled pipeline — import and call `pipeline.invoke(...)` externally
pipeline = build_pipeline()


def run_research(topic: str) -> dict:
    """
    Entry point for the Lexaras research pipeline.

    Args:
        topic: The research topic or question to investigate.

    Returns:
        The final AgentState containing the report, evaluation, and all
        intermediate artefacts. The caller decides what to surface to the user.
    """
    if not topic or not topic.strip():
        raise ValueError("Research topic must be a non-empty string.")

    logger.info("=== Lexaras Pipeline Starting | topic=%r ===", topic)
    overall_start = time.perf_counter()

    initial_state: AgentState = {
        "topic": topic.strip(),
        "search_queries": [],
        "discovered_papers": [],
        "discovery_raw": "",
        "extracted_contexts": [],
        "extraction_errors": [],
        "draft_report": "",
        "evaluation": {},
        "retry_count": 0,
        "error_log": [],
    }

    final_state = pipeline.invoke(initial_state)

    elapsed = time.perf_counter() - overall_start
    score = final_state.get("evaluation", {}).get("overall_score", "N/A")
    logger.info(
        "=== Lexaras Pipeline Complete | topic=%r | score=%s | elapsed=%.2fs ===",
        topic, score, elapsed,
    )

    return final_state
