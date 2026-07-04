import json
import logging
import textwrap
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents_impl.state import AgentState
from agents_impl.llm import llm

logger = logging.getLogger(__name__)


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that Mistral sometimes wraps JSON in."""
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


_EVALUATOR_SYSTEM = textwrap.dedent("""
    You are Lexaras Evaluator — a rigorous quality assurance engine.
    You assess the entire pipeline output and produce an actionable quality score.

    You are impartial and do not inflate scores:
        8+ = genuinely excellent    5 = acceptable    below 4 = significant problems

    EVALUATION DIMENSIONS (each 0-10):
    1. Relevance      — Are papers genuinely on-topic? Penalise off-topic results.
    2. Coverage       — Is the topic comprehensively addressed across sub-topics?
    3. Synthesis      — Does the report find connections across papers, or just list?
    4. Citation       — Is every claim backed by a traceable source with a URL?
    5. Recency        — Are papers recent? Penalise if most are older than 3 years.
                        Google Scholar papers with year metadata are weighted higher.

    OVERALL SCORE formula:
        overall = relevance*0.25 + coverage*0.20 + synthesis*0.25 + citation*0.15 + recency*0.15

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON. No preamble, no markdown fences.
    - improvement_suggestions must be specific, actionable, not vague.
    - recency_score should penalise heavily if most papers are 4+ years old.
""").strip()

_EVALUATOR_HUMAN = textwrap.dedent("""
    Research Topic  : {topic}
    Search Mode     : {search_mode}
    Year Range      : {year_from}–{year_to}

    === PIPELINE SUMMARY ===
    Papers Discovered  : {num_discovered}  (Scholar: {num_scholar} | Web: {num_web})
    Papers Extracted   : {num_extracted}
    Extraction Errors  : {num_errors}
    Error Details      : {errors_summary}
    Year Distribution  : {year_distribution}

    === DRAFTED REPORT ===
    {draft_report}

    === EXTRACTED CONTEXTS (for fact-checking) ===
    {contexts_summary}

    Return your assessment in this exact JSON format:
    {{
        "relevance_score": <0-10>,
        "coverage_score": <0-10>,
        "synthesis_score": <0-10>,
        "citation_score": <0-10>,
        "recency_score": <0-10>,
        "overall_score": <float>,
        "strengths": ["...", "..."],
        "weaknesses": ["...", "..."],
        "improvement_suggestions": ["...", "..."],
        "verdict": "..."
    }}
""").strip()

_evaluator_prompt = ChatPromptTemplate.from_messages([
    ("system", _EVALUATOR_SYSTEM),
    ("human",  _EVALUATOR_HUMAN),
])
_evaluator_chain = _evaluator_prompt | llm | StrOutputParser()


def node_evaluator(state: AgentState) -> AgentState:
    """
    Evaluator node — scores the pipeline output including the new recency dimension.
    Passes year distribution stats so the evaluator can penalise stale paper sets.
    """
    topic     = state["topic"]
    mode      = state["search_mode"]
    year_from = state["year_from"]
    year_to   = state["year_to"]
    draft     = state.get("draft_report", "")
    contexts  = state.get("extracted_contexts",  [])
    errors    = state.get("extraction_errors",   [])
    papers    = state.get("discovered_papers",   [])

    num_scholar = sum(1 for p in papers if p.get("source") == "scholar")
    num_web     = len(papers) - num_scholar

    # Build year distribution string for the evaluator
    years = [
        c.get("publication_year") for c in contexts
        if c.get("publication_year")
    ]
    if years:
        from collections import Counter
        year_counts  = Counter(years)
        year_dist_str = ", ".join(
            f"{yr}: {cnt}" for yr, cnt in sorted(year_counts.items(), reverse=True)
        )
    else:
        year_dist_str = "No year data available"

    ctx_lines: list[str] = []
    for ctx in contexts[:6]:
        year_s = str(ctx.get("publication_year", "?"))
        src_s  = ctx.get("source", "?").upper()
        ctx_lines.append(
            f"- [{src_s} {year_s}] {ctx.get('url','N/A')}: "
            f"{ctx.get('content_summary','')[:200]}…"
        )
    contexts_summary = "\n".join(ctx_lines) if ctx_lines else "No contexts available."

    logger.info("[Evaluator] Starting | topic=%r | mode=%s", topic, mode)
    start = time.perf_counter()

    try:
        raw = _evaluator_chain.invoke({
            "topic":            topic,
            "search_mode":      mode,
            "year_from":        year_from,
            "year_to":          year_to,
            "num_discovered":   len(papers),
            "num_scholar":      num_scholar,
            "num_web":          num_web,
            "num_extracted":    len(contexts),
            "num_errors":       len(errors),
            "errors_summary":   "; ".join(errors[:3]) if errors else "None",
            "year_distribution": year_dist_str,
            "draft_report":     draft[:3000],
            "contexts_summary": contexts_summary,
        })

        cleaned    = _strip_fences(raw)
        evaluation = json.loads(cleaned)
        state["evaluation"] = evaluation

        logger.info(
            "[Evaluator] Complete | overall=%.1f | recency=%s | elapsed=%.2fs",
            evaluation.get("overall_score", 0),
            evaluation.get("recency_score", "?"),
            time.perf_counter() - start,
        )

    except json.JSONDecodeError as exc:
        msg = f"[Evaluator] JSON parse error: {exc}"
        logger.error(msg)
        state["evaluation"] = {
            "error": msg, "overall_score": 0,
            "verdict": "Evaluation failed — could not parse LLM response.",
        }
    except Exception as exc:
        msg = f"[Evaluator] Unexpected error: {exc}"
        logger.error(msg, exc_info=True)
        state["evaluation"] = {
            "error": msg, "overall_score": 0,
            "verdict": "Evaluation failed due to an unexpected error.",
        }

    return state
