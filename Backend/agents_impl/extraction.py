import json
import logging
import textwrap
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from tools import READER_TOOLS
from agents_impl.state import AgentState
from agents_impl.llm import llm

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM = textwrap.dedent("""
    You are Lexaras Extractor — an expert academic reader and knowledge distiller.
    Your job is to deeply read a research paper or article and extract its most
    valuable insights in a structured, citation-aware format.

    OPERATING PRINCIPLES:
    1. Read with the research topic always in mind — extract what is *relevant*,
       not everything on the page.
    2. Identify the paper's thesis, methodology, key findings, and limitations.
    3. Preserve exact claims, statistics, and quantitative results — these are
       the building blocks of a credible research report.
    4. If the page cannot be loaded or is paywalled, say so explicitly in
       content_summary — never fabricate content.
    5. Extract any in-text citations or references that could lead to more papers.

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON. No preamble, no markdown fences.
    - key_points must be full sentences (not fragments).
    - If insufficient content was found, set content_summary to "[INSUFFICIENT_CONTENT]"
      and explain why (paywall, 404, irrelevant page, etc.).
""").strip()

_EXTRACTION_HUMAN = textwrap.dedent("""
    Research Topic: {topic}
    Paper URL: {url}
    Paper Title: {title}
    Initial Snippet: {snippet}

    Please scrape and deeply read the paper at the URL above, then extract:
    1. A 300–500 word content summary focused on relevance to the research topic
    2. 5–8 key findings or claims (as complete sentences)
    3. The research methodology used
    4. Any citations or referenced works found
    5. A clear statement of how this paper relates to: "{topic}"

    Respond in this exact JSON format:
    {{
        "url": "{url}",
        "content_summary": "...",
        "key_points": ["...", "..."],
        "methodology": "...",
        "citations": ["...", "..."],
        "relevance_to_topic": "..."
    }}
""").strip()


def node_extraction(state: AgentState) -> AgentState:
    """
    Extraction node: reads each discovered paper and pulls structured context.
    Processes papers sequentially to avoid rate limiting.
    """
    papers = state.get("discovered_papers", [])
    topic = state["topic"]

    if not papers:
        logger.warning("[Extraction] No papers to extract from.")
        state["extracted_contexts"] = []
        state["extraction_errors"] = []
        return state

    logger.info("[Extraction] Starting | papers=%d | topic=%r", len(papers), topic)
    start = time.perf_counter()

    extraction_agent = create_react_agent(
        model=llm,
        tools=READER_TOOLS,
        prompt=SystemMessage(content=_EXTRACTION_SYSTEM),
    )

    contexts: list[dict] = []
    errors: list[str] = []

    for i, paper in enumerate(papers, start=1):
        url = paper.get("url", "")
        title = paper.get("title", "Unknown Title")
        logger.info("[Extraction] Processing paper %d/%d | url=%s", i, len(papers), url)

        prompt = _EXTRACTION_HUMAN.format(
            topic=topic,
            url=url,
            title=title,
            snippet=paper.get("snippet", ""),
        )

        try:
            result = extraction_agent.invoke({
                "messages": [HumanMessage(content=prompt)]
            })
            raw = result["messages"][-1].content
            cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
            parsed: dict = json.loads(cleaned)

            # Validate minimum quality gate — skip papers with no real content
            summary = parsed.get("content_summary", "")
            if "[INSUFFICIENT_CONTENT]" in summary or len(summary) < 100:
                logger.warning("[Extraction] Low-quality content | url=%s", url)
                errors.append(f"Insufficient content extracted from: {url}")
                continue

            contexts.append(parsed)
            logger.info("[Extraction] Paper %d extracted successfully | url=%s", i, url)

        except json.JSONDecodeError as exc:
            err = f"JSON parse error for {url}: {exc}"
            logger.error("[Extraction] %s", err)
            errors.append(err)

        except Exception as exc:
            err = f"Extraction failed for {url}: {exc}"
            logger.error("[Extraction] %s", err, exc_info=True)
            errors.append(err)

    state["extracted_contexts"] = contexts
    state["extraction_errors"] = errors

    logger.info(
        "[Extraction] Complete | success=%d | errors=%d | elapsed=%.2fs",
        len(contexts),
        len(errors),
        time.perf_counter() - start,
    )
    return state
