import json
import logging
import textwrap
import time

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents_impl.state import AgentState
from agents_impl.llm import academic_llm

logger = logging.getLogger(__name__)

# Below what register_score (out of 10, from the critique pass) do we bother
# spending a second generation pass fixing tone? Set high on purpose — for a
# client-facing report, "good enough" tone isn't the bar.
_REGISTER_REVISION_THRESHOLD = 8


# ── Writer prompt ────────────────────────────────────────────────────────────
#
# The previous version of this prompt described the target tone with three
# adjectives ("authoritative, objective, analytical") and left the model to
# infer everything else. That reliably drifted toward an engaging,
# popular-science voice — plausible synthesis, but not academic register.
#
# This version replaces adjectives with (a) checkable rules and (b) paired
# calibration examples, since showing a model what to avoid alongside what to
# aim for teaches register far more reliably than describing it abstractly.

_WRITER_SYSTEM = textwrap.dedent("""
    You are Lexaras Writer — a senior research analyst producing a formal
    research report for a paying client. You synthesise raw extracted content
    from multiple academic papers into a single, cohesive report written in
    a rigorous academic register.

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

    REGISTER — these are hard rules, not stylistic suggestions:
    - No first-person pronouns ("I", "we", "our") except inside a direct
      quotation from a source.
    - No contractions ("don't", "it's", "can't") — write them in full.
    - No rhetorical questions.
    - No exclamation marks.
    - No casual sentence openers ("So,", "Basically,", "Interestingly,",
      "Anyway,").
    - Hedge only where evidence is genuinely uncertain, and hedge precisely —
      state the specific gap rather than a vague qualifier. Prefer "the most
      recent evidence on X dates to 2021; no more recent study addressing this
      specific question was found" over "it seems X might still hold true."
    - Prefer information-dense sentences over filler lead-ins such as "It is
      important to note that" or "It is worth mentioning that" — state the
      finding directly.

    CALIBRATION EXAMPLES (match the GOOD register; never write like the BAD one):

    BAD:  "It's fascinating how machine learning keeps getting better at
           understanding language every year!"
    GOOD: "Performance on language-understanding benchmarks has improved
           consistently across recent model generations [Smith et al. (2025),
           https://example.org/paper]."

    BAD:  "So what does this all mean for practitioners? Basically, it's time
           to rethink our assumptions."
    GOOD: "These findings indicate that assumptions underlying prior
           methodological frameworks warrant re-examination in light of more
           recent evidence."

    BAD:  "We think this trend will probably continue, though who really
           knows for sure?"
    GOOD: "Whether this trend continues cannot be established from the
           sources reviewed; the most recent data available extends only to
           2024."

    This report will be delivered to a real client. Quality, accuracy, and
    register all matter — a well-synthesised report written in the wrong
    register is still a failed deliverable.
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

    Be rigorous, cite everything, do not pad with filler content, and follow
    the REGISTER rules and calibration examples exactly.
""").strip()

_writer_prompt = ChatPromptTemplate.from_messages([
    ("system", _WRITER_SYSTEM),
    ("human",  _WRITER_HUMAN),
])
_writer_chain = _writer_prompt | academic_llm | StrOutputParser()


# ── Self-critique / revise pass ──────────────────────────────────────────────
#
# Rather than trusting the first generation to reliably hit every register
# rule above, run one cheap, focused critique pass whose only job is to
# check register adherence against the same rules, then — only if needed —
# one revision pass that fixes tone without touching facts or citations.

_CRITIQUE_SYSTEM = textwrap.dedent("""
    You are Lexaras Style Auditor. You review a drafted research report
    against a fixed set of academic-register rules and report violations.
    You do not judge factual accuracy, citation correctness, or content
    completeness — only register/tone.

    REGISTER RULES TO CHECK:
    - No first-person pronouns except inside direct quotations.
    - No contractions.
    - No rhetorical questions.
    - No exclamation marks.
    - No casual sentence openers ("So,", "Basically,", "Interestingly,", "Anyway,").
    - Hedging must be precise (state the specific gap), never vague
      ("it seems", "might", "probably", "who knows").
    - No filler lead-ins ("It is important to note that", "It is worth
      mentioning that").

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON. No preamble, no markdown fences.
    - register_score is 0-10, where 10 means no violations found anywhere.
    - violations is a list of short, specific descriptions (quote the
      offending phrase, do not paraphrase it away).
    - revision_instructions is a single paragraph of concrete, actionable
      fixes for a rewrite pass — not a restatement of the rules.
""").strip()

_CRITIQUE_HUMAN = textwrap.dedent("""
    Draft report to audit:
    {draft}

    Respond in this exact JSON format:
    {{
        "register_score": <0-10>,
        "violations": ["...", "..."],
        "revision_instructions": "..."
    }}
""").strip()

_critique_prompt = ChatPromptTemplate.from_messages([
    ("system", _CRITIQUE_SYSTEM),
    ("human",  _CRITIQUE_HUMAN),
])
_critique_chain = _critique_prompt | academic_llm | StrOutputParser()


_REVISION_SYSTEM = textwrap.dedent("""
    You are Lexaras Writer, now performing a targeted revision pass on your
    own draft. A style auditor has flagged register violations below. Rewrite
    the draft to fix every flagged issue while preserving:
    - All facts, findings, and quantitative details exactly as stated.
    - Every inline citation and the Sources section, unchanged.
    - The overall structure and section headings.

    Do not shorten the report or remove content — only fix tone and register.
    Return the full revised report text. No preamble, no markdown fences
    around the whole response, no commentary about what you changed.
""").strip()

_REVISION_HUMAN = textwrap.dedent("""
    Original draft:
    {draft}

    Style auditor's findings:
    Violations: {violations}
    Revision instructions: {revision_instructions}

    Produce the fully revised report now.
""").strip()

_revision_prompt = ChatPromptTemplate.from_messages([
    ("system", _REVISION_SYSTEM),
    ("human",  _REVISION_HUMAN),
])
_revision_chain = _revision_prompt | academic_llm | StrOutputParser()


def _run_style_critique(draft: str) -> dict:
    """
    Scores a draft against the register rules. Returns a dict with
    register_score / violations / revision_instructions. Never raises —
    on any failure it returns a permissive default so a critique-pass
    failure never blocks the pipeline from delivering the original draft.
    """
    try:
        raw = _critique_chain.invoke({"draft": draft})
        cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
        result: dict = json.loads(cleaned)
        result.setdefault("register_score", 10)
        result.setdefault("violations", [])
        result.setdefault("revision_instructions", "")
        return result
    except Exception as exc:
        logger.warning("[Writer] Style critique failed, skipping revision pass: %s", exc)
        return {"register_score": 10, "violations": [], "revision_instructions": ""}


def _run_revision(draft: str, critique: dict) -> str:
    """
    Produces a register-corrected rewrite. On any failure, returns the
    original draft unchanged — a failed revision pass should never leave
    the pipeline without a report.
    """
    try:
        revised = _revision_chain.invoke({
            "draft": draft,
            "violations": "; ".join(critique.get("violations", [])) or "None listed",
            "revision_instructions": critique.get("revision_instructions", ""),
        })
        return revised.strip()
    except Exception as exc:
        logger.warning("[Writer] Revision pass failed, keeping original draft: %s", exc)
        return draft


def node_writer(state: AgentState) -> AgentState:
    """
    Writer node — synthesises all extracted contexts into the final report,
    then runs a self-critique pass against a fixed academic-register rubric
    and, if needed, a single revision pass to fix tone without touching facts,
    citations, or structure.

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
        draft = _writer_chain.invoke({
            "topic":         topic,
            "search_mode":   mode,
            "year_from":     year_from,
            "year_to":       year_to,
            "num_scholar":   num_scholar,
            "num_web":       num_web,
            "contexts_block": contexts_block,
            "errors_block":  errors_block,
        })

        # Self-critique / revise pass — never allowed to throw past this
        # point; both helpers degrade to "keep the original draft" on failure.
        critique = _run_style_critique(draft)
        register_score = critique.get("register_score", 10)

        if register_score < _REGISTER_REVISION_THRESHOLD:
            logger.info(
                "[Writer] Register score %s below threshold %s — running revision pass | violations=%d",
                register_score, _REGISTER_REVISION_THRESHOLD, len(critique.get("violations", [])),
            )
            final_report = _run_revision(draft, critique)
        else:
            logger.info("[Writer] Register score %s meets threshold — no revision needed", register_score)
            final_report = draft

        state["draft_report"] = final_report
        # Not part of the formal AgentState schema yet, but harmless to carry
        # through at runtime (TypedDict is not enforced) — surfaces register
        # QA in the Debug tab if/when state.py adds these fields formally.
        state["writer_register_score"] = register_score
        state["writer_register_revised"] = register_score < _REGISTER_REVISION_THRESHOLD

        logger.info(
            "[Writer] Complete | chars=%d | register_score=%s | revised=%s | elapsed=%.2fs",
            len(final_report), register_score, state["writer_register_revised"],
            time.perf_counter() - start,
        )
    except Exception as exc:
        msg = f"[Writer] Failed: {exc}"
        logger.error(msg, exc_info=True)
        state["error_log"]    = state.get("error_log", []) + [msg]
        state["draft_report"] = f"[WRITER_ERROR] Report generation failed: {exc}"

    return state