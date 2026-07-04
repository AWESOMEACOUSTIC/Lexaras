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
       Use inline citations in the format [Authors (Year), URL] after each claim.
       For Scholar papers, include the publication year and authors.
    2. SYNTHESIS OVER SUMMARY: Do not just list what each paper says. Find the
       common threads, contrasts, and cumulative story they tell together.
    3. RECENCY AWARENESS: Highlight where recent papers (last 1-2 years) confirm,
       challenge, or extend older findings. If the most recent papers are from
       Google Scholar, note that they are peer-reviewed.
    4. STRUCTURE: Use clear H2 headings, bullet points for findings, and prose
       paragraphs for interpretation. Readable by both expert and non-specialist.
    5. NO FABRICATION: If extracted contexts do not contain enough information
       to make a claim, say so explicitly. Never fill gaps with assumptions.
    6. TONE: Authoritative, objective, analytical. Flag uncertainty explicitly.

    This report will be delivered to a real client. Quality and accuracy matter.
""").strip()

_WRITER_HUMAN = textwrap.dedent("""
    Research Topic : {topic}
    Search Mode    : {search_mode}
    Year Range     : {year_from} – {year_to}
    Scholar Papers : {num_scholar}
    Web Papers     : {num_web}

    Extracted Paper Contexts:
    {contexts_block}

    Papers that failed to extract (note limitations):
    {errors_block}

    Write a comprehensive research report structured as:

    ## Introduction
    (150-200 words: frame the topic, why it matters, what this report covers,
     and note the search strategy — e.g. "X of Y papers are peer-reviewed
     Google Scholar results from {year_from}–{year_to}")

    ## Papers Analysed
    (For each paper: title, authors (year), URL, one sentence on why selected,
     and whether it is a peer-reviewed Scholar result or a web source)

    ## Key Findings
    (Minimum 6 detailed findings synthesised across all papers. Each finding:
     - Bold heading capturing the core insight
     - 2-4 sentences with evidence and quantitative detail where available
     - Inline citation: [Authors (Year), URL])

    ## Synthesis & Implications
    (200-300 words: What does the combined body of research tell us?
     What changed recently vs older findings? What are the open questions?
     What should practitioners or researchers do next?)

    ## Limitations of This Report
    (Gaps, failed extractions, paywalled papers, topic areas not covered,
     and any caveats about source diversity)

    ## Sources
    (Numbered list: [N] Authors (Year). Title. URL. [Scholar/Web])

    Be rigorous, cite everything, and do not pad with filler content.
""").strip()

_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", _WRITER_SYSTEM),
    ("human",  _WRITER_HUMAN),
])
_writer_chain = _writer_prompt | creative_llm | StrOutputParser()


def node_writer(state: AgentState) -> AgentState:
    """
    Writer node — synthesises all extracted contexts into the final report.
    Passes Scholar vs web paper counts and year range to the prompt so the
    writer can explicitly discuss the source mix and recency profile.
    """
    contexts = state.get("extracted_contexts", [])
    errors   = state.get("extraction_errors",  [])
    topic    = state["topic"]
    mode     = state["search_mode"]
    year_from = state["year_from"]
    year_to   = state["year_to"]

    num_scholar = sum(1 for c in contexts if c.get("source") == "scholar")
    num_web     = len(contexts) - num_scholar

    logger.info(
        "[Writer] Starting | contexts=%d (scholar=%d web=%d) | topic=%r",
        len(contexts), num_scholar, num_web, topic,
    )
    start = time.perf_counter()

    if not contexts:
        state["draft_report"] = (
            f"# Research Report: {topic}\n\n"
            "**⚠ No content could be extracted from the discovered papers.**\n\n"
            "Errors encountered:\n" + "\n".join(f"- {e}" for e in errors)
        )
        return state

    contexts_block_parts: list[str] = []
    for i, ctx in enumerate(contexts, start=1):
        kp_str   = "\n".join(f"  • {kp}" for kp in ctx.get("key_points", []))
        cite_str = "\n".join(f"  • {c}"  for c  in ctx.get("citations",   [])[:5])
        year_str = str(ctx.get("publication_year", "Unknown"))
        part = textwrap.dedent(f"""
            --- Paper {i} ({ctx.get('source','').upper()}) ---
            Title    : {ctx.get('title', 'N/A')}
            Authors  : {ctx.get('authors', 'Unknown')}
            Year     : {year_str}
            URL      : {ctx.get('url', 'N/A')}
            SUMMARY  : {ctx.get('content_summary', '')}
            METHODOLOGY: {ctx.get('methodology', 'Not specified')}
            KEY POINTS:
            {kp_str}
            RELEVANCE: {ctx.get('relevance_to_topic', '')}
            CITED WORKS:
            {cite_str}
        """).strip()
        contexts_block_parts.append(part)

    contexts_block = "\n\n".join(contexts_block_parts)
    errors_block   = "\n".join(f"- {e}" for e in errors) if errors else "None"

    try:
        report = _writer_chain.invoke({
            "topic":         topic,
            "search_mode":   mode,
            "year_from":     year_from,
            "year_to":       year_to,
            "num_scholar":   num_scholar,
            "num_web":       num_web,
            "contexts_block": contexts_block,
            "errors_block":  errors_block,
        })
        state["draft_report"] = report
        logger.info(
            "[Writer] Complete | chars=%d | elapsed=%.2fs",
            len(report), time.perf_counter() - start,
        )
    except Exception as exc:
        msg = f"[Writer] Failed: {exc}"
        logger.error(msg, exc_info=True)
        state["error_log"]    = state.get("error_log", []) + [msg]
        state["draft_report"] = f"[WRITER_ERROR] Report generation failed: {exc}"

    return state
