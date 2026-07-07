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
    6. Register       — Does the FINAL report text hold a rigorous academic register
                        throughout? Judge this yourself, directly against the report
                        text below — do not defer to any writer self-assessment you
                        are given as context. Score 10 only if none of the following
                        appear anywhere in the report:
                          - First-person pronouns ("I", "we", "our") outside a
                            direct quotation from a source.
                          - Contractions ("don't", "it's", "can't").
                          - Rhetorical questions.
                          - Exclamation marks.
                          - Casual sentence openers ("So,", "Basically,",
                            "Interestingly,", "Anyway,").
                          - Vague hedging ("it seems", "might", "probably",
                            "who knows") where precise hedging was possible
                            (e.g. naming the specific year/gap in evidence instead).
                          - Filler lead-ins ("It is important to note that",
                            "It is worth mentioning that").
                        Deduct roughly 1-2 points per distinct violation type found,
                        more if a violation recurs throughout the report rather than
                        appearing once.

    OVERALL SCORE formula:
        overall = relevance*0.20 + coverage*0.15 + synthesis*0.20 + citation*0.15
                 + recency*0.15 + register*0.15

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON. No preamble, no markdown fences.
    - improvement_suggestions must be specific, actionable, not vague.
    - recency_score should penalise heavily if most papers are 4+ years old.
    - register_score must be justified by at least one specific example (a quoted
      phrase from the report) in weaknesses if it is below 8 — do not dock points
      without pointing to what triggered the deduction.
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

    === WRITER SELF-ASSESSMENT (context only — verify independently, do not defer) ===
    Pre-revision register self-score : {writer_register_score}
    Automatic revision pass applied  : {writer_register_revised}
    Note: this is the writer's own judgment of its first draft, before any
    revision pass ran. It may be optimistic, or the revision pass itself may
    have introduced new issues. Score register_score entirely from the actual
    report text below.

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
        "register_score": <0-10>,
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
    Evaluator node — scores the pipeline output across relevance, coverage,
    synthesis, citation, recency, and register.

    Register is judged independently here, directly from the final report
    text, even though the writer node already runs its own self-critique
    pass (see writer.py). The two are intentionally separate checks: the
    writer's self-critique is a cheap, in-process pass that can revise before
    the report ships; this evaluator pass is the independent, ground-truth
    quality gate that doesn't trust the writer's own grading of itself.
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

    # Writer self-assessment, passed through as context only (see prompt note
    # instructing the evaluator not to defer to it). Both are optional — an
    # older run, or a run where the writer's critique pass itself failed and
    # degraded gracefully, may leave these unset.
    writer_register_score = state.get("writer_register_score")
    writer_register_score_str = (
        str(writer_register_score) if writer_register_score is not None
        else "Not available (self-critique did not run or was not recorded)"
    )
    writer_register_revised = state.get("writer_register_revised")
    writer_register_revised_str = (
        str(writer_register_revised) if writer_register_revised is not None
        else "Unknown"
    )

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
            "writer_register_score":    writer_register_score_str,
            "writer_register_revised":  writer_register_revised_str,
            "draft_report":     draft[:3000],
            "contexts_summary": contexts_summary,
        })

        cleaned    = _strip_fences(raw)
        evaluation = json.loads(cleaned)
        state["evaluation"] = evaluation

        logger.info(
            "[Evaluator] Complete | overall=%.1f | recency=%s | register=%s | elapsed=%.2fs",
            evaluation.get("overall_score", 0),
            evaluation.get("recency_score", "?"),
            evaluation.get("register_score", "?"),
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