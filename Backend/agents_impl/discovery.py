import json
import logging
import textwrap
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from tools import DISCOVERY_TOOLS
from agents_impl.state import AgentState
from agents_impl.llm import llm

logger = logging.getLogger(__name__)

_DISCOVERY_SYSTEM = textwrap.dedent("""
    You are Lexaras Discovery — a specialised academic research intelligence agent.
    Your sole responsibility is to find the most relevant, high-quality research
    papers and authoritative sources for a given topic.

    OPERATING PRINCIPLES:
    1. Think like a research librarian with deep domain expertise.
    2. Generate 2–4 distinct, complementary search queries that together cover the
       topic from different angles (theoretical, empirical, recent advances, key authors).
    3. Prioritise academic sources: arXiv, PubMed, Semantic Scholar, Google Scholar
       results, IEEE, ACM, Springer, Nature, JSTOR. Also accept high-quality
       technical blogs, government datasets, and landmark industry white papers.
    4. Critically evaluate each result: does it directly address the topic, or is
       it tangentially related? Be selective — 5 highly relevant papers beat 20
       loosely related ones.
    5. For each accepted paper, write a one-sentence relevance_note explaining
       *why* this paper matters for the specific topic.

    OUTPUT CONSTRAINTS:
    - Return ONLY valid JSON matching the specified schema. No preamble, no markdown.
    - Maximum 8 papers. Minimum 3. If fewer than 3 are found, flag in relevance_note.
    - Deduplicate: never return the same URL twice.
""").strip()

_DISCOVERY_HUMAN = textwrap.dedent("""
    Research Topic: {topic}

    Execute a multi-angle search strategy and return the most relevant academic
    papers and sources. For each paper include: title, url, snippet (150–250 words
    summarising its relevance), and relevance_note (1 sentence on why it matters).

    Respond in this exact JSON format:
    {{
        "search_queries": ["query 1", "query 2", "query 3"],
        "papers": [
            {{
                "title": "...",
                "url": "...",
                "snippet": "...",
                "relevance_note": "..."
            }}
        ]
    }}
""").strip()


def node_discovery(state: AgentState) -> AgentState:
    """
    Discovery node: searches the web and identifies relevant papers.
    Uses a ReAct agent so it can iteratively refine its queries.
    """
    topic = state["topic"]
    logger.info("[Discovery] Starting | topic=%r", topic)
    start = time.perf_counter()

    # Build a ReAct agent with only the search tool
    discovery_agent = create_react_agent(
        model=llm,
        tools=DISCOVERY_TOOLS,
        prompt=SystemMessage(content=_DISCOVERY_SYSTEM),
    )

    # The agent runs, calls web_search as many times as it needs, then
    # returns a final message. We extract the last AIMessage.
    try:
        result = discovery_agent.invoke({
            "messages": [HumanMessage(content=_DISCOVERY_HUMAN.format(topic=topic))]
        })
        raw_output = result["messages"][-1].content
        state["discovery_raw"] = raw_output

        # Parse the structured JSON response
        # Strip markdown code fences if the model wrapped the JSON
        cleaned = raw_output.strip().removeprefix("```json").removesuffix("```").strip()
        parsed: dict = json.loads(cleaned)

        state["search_queries"] = parsed.get("search_queries", [])
        state["discovered_papers"] = parsed.get("papers", [])

        logger.info(
            "[Discovery] Complete | queries=%d | papers=%d | elapsed=%.2fs",
            len(state["search_queries"]),
            len(state["discovered_papers"]),
            time.perf_counter() - start,
        )

    except json.JSONDecodeError as exc:
        msg = f"[Discovery] JSON parse error: {exc} | raw={raw_output[:200]}"
        logger.error(msg)
        state["error_log"] = state.get("error_log", []) + [msg]
        state["discovered_papers"] = []

    except Exception as exc:
        msg = f"[Discovery] Unexpected error: {exc}"
        logger.error(msg, exc_info=True)
        state["error_log"] = state.get("error_log", []) + [msg]
        state["discovered_papers"] = []

    return state
