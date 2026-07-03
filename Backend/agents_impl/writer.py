import logging
import textwrap
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents_impl.state import AgentState
from agents_impl.llm import creative_llm

logger = logging.getLogger(__name__)

_WRITER_SYSTEM = textwrap.dedent("""
    You are Lexaras Writer — a senior research analyst and science communicator.
    You synthesise raw extracted content from multiple academic papers into a
    single, cohesive, professionally written research report.

    WRITING STANDARDS:
    1. ACCURACY FIRST: Every claim must be traceable to a specific source paper.
       Use inline citations in the format [Author/Title, URL] after each claim.
    2. SYNTHESIS OVER SUMMARY: Do not just list what each paper says. Find the
       common threads, contrasts, and cumulative story they tell together.
    3. STRUCTURE: Use clear H2 headings, bullet points for findings, and prose
       paragraphs for interpretation. The report must be readable by both a
       technical expert and an informed non-specialist.
    4. NO FABRICATION: If the extracted contexts do not contain enough information
       to make a claim, say so explicitly rather than filling gaps with assumptions.
    5. TONE: Authoritative, objective, analytical. Avoid hedging language like
       "it seems" or "perhaps" unless genuinely uncertain — and flag uncertainty
       explicitly when it exists.

    The report will be delivered to a real client. Quality and accuracy matter
    more than length.
""").strip()

_WRITER_HUMAN = textwrap.dedent("""
    Research Topic: {topic}

    Extracted Paper Contexts:
    {contexts_block}

    Papers that failed to extract (note these limitations):
    {errors_block}

    Write a comprehensive research report structured as:

    ## Introduction
    (150–200 words: frame the topic, why it matters, what this report covers)

    ## Papers Analysed
    (Brief list: title, URL, one sentence on why it was selected)

    ## Key Findings
    (Minimum 6 detailed findings synthesised across all papers. Each finding:
     - A bold heading capturing the insight
     - 2–4 sentences explaining the finding with evidence
     - Inline citation: [Paper Title, URL])

    ## Synthesis & Implications
    (200–300 words: What does the combined body of research tell us?
     What are the open questions? What should practitioners or researchers do next?)

    ## Limitations of This Report
    (Any gaps, failed extractions, or topic areas not covered)

    ## Sources
    (Numbered list of all URLs used)

    Be rigorous, cite everything, and do not pad with filler content.
""").strip()

_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", _WRITER_SYSTEM),
    ("human", _WRITER_HUMAN),
])

_writer_chain = _writer_prompt | creative_llm | StrOutputParser()


def node_writer(state: AgentState) -> AgentState:
    """
    Writer node: synthesises all extracted contexts into a final report.
    Uses an LCEL chain (no tools needed — pure text generation).
    """
    contexts = state.get("extracted_contexts", [])
    errors = state.get("extraction_errors", [])
    topic = state["topic"]

    logger.info("[Writer] Starting | contexts=%d | topic=%r", len(contexts), topic)
    start = time.perf_counter()

    if not contexts:
        state["draft_report"] = (
            f"# Research Report: {topic}\n\n"
            "**⚠ No content could be extracted from the discovered papers.**\n\n"
            "Errors encountered:\n" + "\n".join(f"- {e}" for e in errors)
        )
        return state

    # Build the contexts block for the prompt
    contexts_block_parts: list[str] = []
    for i, ctx in enumerate(contexts, start=1):
        key_points_str = "\n".join(f"  • {kp}" for kp in ctx.get("key_points", []))
        citations_str = "\n".join(f"  • {c}" for c in ctx.get("citations", [])[:5])
        part = textwrap.dedent(f"""
            --- Paper {i} ---
            URL: {ctx.get('url', 'N/A')}
            SUMMARY: {ctx.get('content_summary', '')}
            METHODOLOGY: {ctx.get('methodology', 'Not specified')}
            KEY POINTS:
            {key_points_str}
            RELEVANCE TO TOPIC: {ctx.get('relevance_to_topic', '')}
            CITED WORKS:
            {citations_str}
        """).strip()
        contexts_block_parts.append(part)

    contexts_block = "\n\n".join(contexts_block_parts)
    errors_block = "\n".join(f"- {e}" for e in errors) if errors else "None"

    try:
        report = _writer_chain.invoke({
            "topic": topic,
            "contexts_block": contexts_block,
            "errors_block": errors_block,
        })
        state["draft_report"] = report
        logger.info(
            "[Writer] Complete | chars=%d | elapsed=%.2fs",
            len(report),
            time.perf_counter() - start,
        )
    except Exception as exc:
        msg = f"[Writer] Failed to generate report: {exc}"
        logger.error(msg, exc_info=True)
        state["error_log"] = state.get("error_log", []) + [msg]
        state["draft_report"] = f"[WRITER_ERROR] Report generation failed: {exc}"

    return state
