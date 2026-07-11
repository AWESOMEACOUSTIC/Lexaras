import json
import logging
import textwrap
import time
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from tools import READER_TOOLS
from agents_impl.state import AgentState
from agents_impl.llm import llm
from tools_impl.helpers import CONTENT_QUALITY_FLAG_PREFIX
from tools_impl.domain_reputation import record_outcome, is_domain_blocked

logger = logging.getLogger(__name__)


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences that Mistral sometimes wraps JSON in."""
    return raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


_EXTRACTION_SYSTEM = textwrap.dedent("""
    You are Lexaras Extractor — an expert academic reader and knowledge distiller.
    Your job is to deeply read a research paper or article and extract its most
    valuable insights in a structured, citation-aware format.

    OPERATING PRINCIPLES:
    0. BEFORE summarizing, classify what you actually scraped. Set content_type to:
       - "paper_content"  — the full paper or a substantial portion of it
       - "abstract_only"  — only an abstract/teaser is visible (e.g. paywalled)
       - "access_wall"    — page is dominated by sign-in, purchase, cookie-consent,
                            or "enable JavaScript" messaging
       - "unrelated_page" — a homepage, error page, listing page, or content that
                            does not match the paper title
       Also rate topic_relevance ("high", "medium", "low", "none") based on how
       well the ACTUAL scraped content relates to the research topic — not the
       title or snippet.
       If a tool result begins with a line starting "CONTENT_QUALITY_FLAG:",
       treat that as authoritative — it means an automated check already
       determined the page is an access wall or low-quality scrape. Set
       content_type to "access_wall" (or "unrelated_page" if the flag reason
       indicates unrelated/garbage text) accordingly, even if the remaining
       text looks superficially readable.
       If content_type is "access_wall" or "unrelated_page", or topic_relevance
       is "low" or "none", leave content_summary/key_points/methodology EMPTY.
       Reporting an unusable page correctly is a SUCCESS, not a failure.
    1. Read with the research topic always in mind — extract what is *relevant*,
       not everything on the page.
    2. Identify the paper's thesis, methodology, key findings, and limitations.
    3. Preserve exact claims, statistics, and quantitative results — these are
       the building blocks of a credible research report.
    4. If the page cannot be loaded, is paywalled, or returns insufficient content,
       say so explicitly in content_summary — NEVER fabricate content.
    5. For Scholar papers, prefer the direct PDF link over the landing page when
       available — PDFs contain the full paper text.
    6. For SCHOLAR papers where the URL cannot be scraped (paywall, JS-rendered
       SPA, empty page), you may use the provided Initial Snippet (which is the
       abstract from Google Scholar) to create a minimal extraction. In this case:
       - Set content_summary to a summary based ONLY on the snippet text.
       - Prefix content_summary with "[ABSTRACT_ONLY] ".
       - key_points should be derived from what the snippet actually says.
       - methodology should be "Not available — abstract only".
       - Do NOT invent claims beyond what the snippet states.
    7. Extract any in-text citations or references that could lead to more papers.

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON. No preamble, no markdown fences.
    - key_points must be full sentences (not fragments or headlines).
    - If insufficient content was found AND no usable snippet is available,
      set content_summary to "[INSUFFICIENT_CONTENT]" and explain why.
""").strip()

_EXTRACTION_HUMAN = textwrap.dedent("""
    Research Topic : {topic}
    Paper Title    : {title}
    Paper URL      : {url}
    Source         : {source}
    Published Year : {pub_year}
    Authors        : {authors}
    Initial Snippet: {snippet}

    Scrape and deeply read the paper at the URL above, then extract:
    1. A 300-500 word content summary focused on relevance to the research topic
    2. 5-8 key findings or claims (as complete sentences with quantitative detail where available)
    3. The research methodology used (study design, sample size, data sources, etc.)
    4. Any citations or referenced works found in the text
    5. A clear statement of how this paper specifically relates to: "{topic}"

    Respond in this exact JSON format:
    {{
        "url": "{url}",
        "content_type": "paper_content | abstract_only | access_wall | unrelated_page",
        "topic_relevance": "high | medium | low | none",
        "content_summary": "...",
        "key_points": ["...", "..."],
        "methodology": "...",
        "citations": ["...", "..."],
        "relevance_to_topic": "..."
    }}
""").strip()


_WALL_MARKERS = (
    "sign in to read", "purchase access", "institutional login",
    "buy this article", "access through your institution",
    "we use cookies", "cookie consent", "accept all cookies",
    "subscribe to continue", "javascript is required",
    "enable javascript",
)


def _looks_like_wall(text: str) -> bool:
    """
    Cheap backstop in case the LLM misclassifies a wall as content. This
    checks the LLM's OWN SUMMARY text — kept as a redundant, cheap second
    layer, but note it is weaker than the deterministic raw-content check
    below (`_raw_output_flagged_quality_issue`), since a paraphrased summary
    of a wall page may not reuse these exact phrases. Both checks run;
    either one can reject.
    """
    lowered = text.lower()
    hits = sum(m in lowered for m in _WALL_MARKERS)
    return hits >= 2 or (hits >= 1 and len(text) < 2000)


def _raw_tool_output_flagged_quality_issue(messages: list) -> tuple[bool, str]:
    """
    Scans the ReAct agent's actual ToolMessage history (i.e. what scrape_url
    / extract_pdf literally returned) for the CONTENT_QUALITY_FLAG marker
    that the tool layer stamps on raw, pre-summarization text (see
    tools_impl/helpers.py's `_quality_gate` / `_gate_and_prefix`).

    This is deterministic and independent of what the extraction LLM later
    claims in its structured output — it cannot be talked past by a
    confident-sounding but wrong `content_type: "paper_content"` classification,
    because it never looks at the LLM's summary at all, only at the raw tool
    return value.
    """
    for m in messages:
        if isinstance(m, ToolMessage):
            content = m.content if isinstance(m.content, str) else str(m.content)
            if CONTENT_QUALITY_FLAG_PREFIX in content:
                # Grab the flag line itself for a specific, loggable reason.
                for line in content.splitlines():
                    if line.startswith(CONTENT_QUALITY_FLAG_PREFIX):
                        return True, line[len(CONTENT_QUALITY_FLAG_PREFIX):].strip()
                return True, "flag detected (reason line not found)"
    return False, ""


def node_extraction(state: AgentState) -> AgentState:
    """
    Extraction node — reads each discovered paper and pulls structured context.
    Processes papers sequentially to respect rate limits on external servers.
    Scholar papers carry extra metadata (authors, year) injected into the prompt
    so the extractor can mention them explicitly in summaries.

    Runs a defense-in-depth quality gate on top of the LLM's own self-reported
    content_type/topic_relevance:
      1. A deterministic check of the raw tool output for a CONTENT_QUALITY_FLAG
         stamped by the tool layer itself (wall-marker + structural checks on
         the actual scraped text) — this can override an LLM's incorrect claim.
      2. The pre-existing `_looks_like_wall` check on the LLM's own summary, as
         a cheap secondary backstop.

    Also records each attempt's outcome to the domain-reputation cache
    (tools_impl/domain_reputation.py) so discovery can learn, over time, which
    domains are reliably extractable and which aren't.
    """
    papers = state.get("discovered_papers", [])
    topic  = state["topic"]

    if not papers:
        logger.warning("[Extraction] No papers to extract from.")
        state["extracted_contexts"] = []
        state["extraction_errors"]  = []
        state["recommended_reading"] = []
        return state

    logger.info("[Extraction] Starting | papers=%d | topic=%r", len(papers), topic)
    start = time.perf_counter()

    extraction_agent = create_react_agent(
        model=llm,
        tools=READER_TOOLS,
        prompt=SystemMessage(content=_EXTRACTION_SYSTEM),
    )

    contexts: list[dict] = []
    errors:   list[str]  = []

    for i, paper in enumerate(papers, start=1):
        url      = paper.get("url", "")
        title    = paper.get("title", "Unknown Title")
        source   = paper.get("source", "unknown")
        pub_year = paper.get("publication_year")
        authors  = paper.get("authors", "Unknown")

        logger.info(
            "[Extraction] Paper %d/%d | source=%s | year=%s | url=%s",
            i, len(papers), source, pub_year, url,
        )

        tldr = paper.get("tldr")
        snippet = paper.get("snippet", "")
        if tldr:
            snippet = f"{snippet}\n\nSemantic Scholar TLDR: {tldr}"

        prompt = _EXTRACTION_HUMAN.format(
            topic    = topic,
            title    = title,
            url      = url,
            source   = source.upper(),
            pub_year = pub_year or "Unknown",
            authors  = authors or "Unknown",
            snippet  = snippet,
        )

        try:
            if is_domain_blocked(url) and paper.get("oa_status") != "found":
                logger.info("[Extraction] Skipping scrape for blocked paywall domain | url=%s", url)
                content_type = "access_wall"
                relevance = "medium"
                usable = False
                raw_flagged = False
                summary = "[BLOCKED_PAYWALL]"
                parsed = {}
            else:
                result  = extraction_agent.invoke({
                    "messages": [HumanMessage(content=prompt)]
                })
                raw     = result["messages"][-1].content
                cleaned = _strip_fences(raw)
                parsed = json.loads(cleaned)

                summary        = parsed.get("content_summary", "")
                content_type   = parsed.get("content_type", "paper_content")
                relevance      = parsed.get("topic_relevance", "high")

                raw_flagged, raw_flag_reason = _raw_tool_output_flagged_quality_issue(
                    result["messages"]
                )

                usable = (
                    content_type in ("paper_content", "abstract_only")
                    and relevance in ("high", "medium")
                    and "[INSUFFICIENT_CONTENT]" not in summary
                    and len(summary) >= 100
                    and not _looks_like_wall(summary)
                    and not raw_flagged
                )

            if not usable:
                # ── Snippet-based fallback for Scholar papers ──────────────
                snippet_text = snippet.strip()
                # Only fall back for access problems — if the content was read
                # and judged off-topic, the snippet won't rescue it.
                access_problem = (
                    content_type in ("access_wall", "unrelated_page")
                    or "[INSUFFICIENT_CONTENT]" in summary
                    or len(summary) < 100
                    or raw_flagged
                    or summary == "[BLOCKED_PAYWALL]"
                )
                if source == "scholar" and len(snippet_text) > 50 and access_problem:
                    logger.info(
                        "[Extraction] Using snippet fallback for Scholar paper | url=%s",
                        url,
                    )
                    parsed = {
                        "url":                url,
                        "content_type":       "abstract_only",
                        "topic_relevance":    "medium",
                        "content_summary":    f"[ABSTRACT_ONLY] {snippet_text}",
                        "key_points":         [snippet_text] if snippet_text else [],
                        "methodology":        "Not available — abstract only",
                        "citations":          [],
                        "relevance_to_topic": paper.get("relevance_note", "Relevance assessment unavailable."),
                        "source":             source,
                        "publication_year":   pub_year,
                        "authors":            authors,
                        "title":              title,
                        "evidence_level":     "abstract_only",
                    }
                    contexts.append(parsed)
                    # The scrape itself still failed (that's why we fell
                    # back) — record it as a domain failure even though the
                    # paper survives via the snippet.
                    record_outcome(url, success=False)
                    continue

                reason_detail = f" (raw-content flag: {raw_flag_reason})" if (not summary == "[BLOCKED_PAYWALL]" and raw_flagged) else ""
                logger.warning(
                    "[Extraction] Rejected | type=%s relevance=%s url=%s%s",
                    content_type, relevance, url, reason_detail,
                )
                errors.append(
                    f"Unusable content from: {url} "
                    f"(source: {source}, type: {content_type}, relevance: {relevance})"
                    f"{reason_detail}"
                )
                
                # Add to recommended reading if it was somewhat relevant
                if relevance in ("high", "medium") or summary == "[BLOCKED_PAYWALL]":
                    rec_list = state.setdefault("recommended_reading", [])
                    rec_list.append(paper)
                    
                record_outcome(url, success=False)
                continue

            # Enrich parsed context with paper metadata for the writer
            parsed["source"]           = source
            parsed["publication_year"] = pub_year
            parsed["authors"]          = authors
            parsed["title"]            = title
            parsed["evidence_level"]   = (
                "abstract_only" if content_type == "abstract_only" else "full_text"
            )

            contexts.append(parsed)
            record_outcome(url, success=True)
            logger.info("[Extraction] Success | paper=%d | url=%s", i, url)

        except json.JSONDecodeError as exc:
            err = f"JSON parse error for {url}: {exc}"
            logger.error("[Extraction] %s", err)
            errors.append(err)
            record_outcome(url, success=False)

        except Exception as exc:
            err = f"Extraction failed for {url}: {exc}"
            logger.error("[Extraction] %s", err, exc_info=True)
            errors.append(err)
            record_outcome(url, success=False)

    state["extracted_contexts"] = contexts
    state["extraction_errors"]  = errors

    logger.info(
        "[Extraction] Complete | success=%d | errors=%d | elapsed=%.2fs",
        len(contexts), len(errors), time.perf_counter() - start,
    )
    return state