import json
import logging
import textwrap
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents_impl.state import AgentState
from agents_impl.llm import llm

logger = logging.getLogger(__name__)

_EVALUATOR_SYSTEM = textwrap.dedent("""
    You are Lexaras Evaluator — a rigorous quality assurance engine for AI-generated
    research pipelines. Your role is to assess the entire pipeline output — from
    paper discovery through to the final report — and produce an actionable,
    quantitative quality score.

    You are impartial, thorough, and do not inflate scores. A score of 8+ means
    genuinely excellent work. A score of 5 means acceptable but improvable.
    A score below 4 means the output has significant problems.

    EVALUATION DIMENSIONS:
    1. Relevance (0–10): Are the discovered and extracted papers genuinely relevant
       to the stated topic? Are off-topic papers included?
    2. Coverage (0–10): Does the report address the topic comprehensively, or are
       important sub-topics or perspectives missing?
    3. Synthesis Quality (0–10): Does the writer synthesise ideas across papers,
       or merely summarise each one individually? Are there insightful connections?
    4. Citation Integrity (0–10): Is every claim backed by a traceable source?
       Are URLs valid and present? Is there any content that appears fabricated?

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON. No preamble, no markdown fences.
    - overall_score = (relevance*0.3 + coverage*0.25 + synthesis*0.3 + citation*0.15)
    - improvement_suggestions must be specific and actionable, not vague.
""").strip()

_EVALUATOR_HUMAN = textwrap.dedent("""
    Research Topic: {topic}

    === PIPELINE SUMMARY ===
    Papers Discovered: {num_discovered}
    Papers Successfully Extracted: {num_extracted}
    Extraction Errors: {num_errors}
    Error Details: {errors_summary}

    === DRAFTED REPORT ===
    {draft_report}

    === EXTRACTED CONTEXTS (for fact-checking) ===
    {contexts_summary}

    Please evaluate the pipeline output. Return your assessment in this exact JSON format:
    {{
        "relevance_score": <0-10>,
        "coverage_score": <0-10>,
        "synthesis_score": <0-10>,
        "citation_score": <0-10>,
        "overall_score": <float>,
        "strengths": ["...", "..."],
        "weaknesses": ["...", "..."],
        "improvement_suggestions": ["...", "..."],
        "verdict": "..."
    }}
""").strip()

_evaluator_prompt = ChatPromptTemplate.from_messages([
    ("system", _EVALUATOR_SYSTEM),
    ("human", _EVALUATOR_HUMAN),
])

_evaluator_chain = _evaluator_prompt | llm | StrOutputParser()


def node_evaluator(state: AgentState) -> AgentState:
    """
    Evaluator node: scores the entire pipeline output and provides feedback.
    """
    topic = state["topic"]
    draft = state.get("draft_report", "")
    contexts = state.get("extracted_contexts", [])
    errors = state.get("extraction_errors", [])
    papers = state.get("discovered_papers", [])

    logger.info("[Evaluator] Starting | topic=%r", topic)
    start = time.perf_counter()

    # Build a compact contexts summary for the evaluator prompt
    ctx_lines: list[str] = []
    for ctx in contexts[:5]:   # cap at 5 to stay within token budget
        ctx_lines.append(f"- {ctx.get('url', 'N/A')}: {ctx.get('content_summary', '')[:200]}…")
    contexts_summary = "\n".join(ctx_lines) if ctx_lines else "No contexts available."

    try:
        raw = _evaluator_chain.invoke({
            "topic": topic,
            "num_discovered": len(papers),
            "num_extracted": len(contexts),
            "num_errors": len(errors),
            "errors_summary": "; ".join(errors[:3]) if errors else "None",
            "draft_report": draft[:3000],   # truncate to avoid prompt overflow
            "contexts_summary": contexts_summary,
        })

        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        evaluation: dict = json.loads(cleaned)
        state["evaluation"] = evaluation

        logger.info(
            "[Evaluator] Complete | overall_score=%.1f | elapsed=%.2fs",
            evaluation.get("overall_score", 0),
            time.perf_counter() - start,
        )

    except json.JSONDecodeError as exc:
        msg = f"[Evaluator] JSON parse error: {exc}"
        logger.error(msg)
        state["evaluation"] = {
            "error": msg,
            "overall_score": 0,
            "verdict": "Evaluation failed — could not parse LLM response.",
        }
    except Exception as exc:
        msg = f"[Evaluator] Unexpected error: {exc}"
        logger.error(msg, exc_info=True)
        state["evaluation"] = {
            "error": msg,
            "overall_score": 0,
            "verdict": "Evaluation failed due to an unexpected error.",
        }

    return state
