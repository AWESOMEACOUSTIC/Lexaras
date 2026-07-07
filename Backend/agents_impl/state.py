from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class PaperMeta(TypedDict):
    """Metadata for one discovered paper — uniform across Scholar and web sources."""
    title:            str
    url:              str
    snippet:          str
    relevance_note:   str
    source:           str            # "scholar" | "web"
    publication_year: Optional[int]  # None when unavailable
    authors:          Optional[str]  # None when unavailable


class AgentState(TypedDict):
    """
    Single shared object that flows through every graph node.
    Every field has a named owner and a documented lifecycle.
    """
    # ── User inputs
    topic:       str
    search_mode: Literal["default", "scholar_only"]  # set by run_research()
    year_from:   int   # floor year for Scholar windows  (current_year - SCHOLAR_YEARS)
    year_to:     int   # ceiling year                    (current_year)

    # ── Discovery outputs
    scholar_papers:    list[PaperMeta]   # papers found via Google Scholar
    web_papers:        list[PaperMeta]   # papers found via Tavily (default mode only)
    discovered_papers: list[PaperMeta]  # combined, deduped, ordered newest-first
    search_queries:    list[str]         # all queries that were fired
    discovery_raw:     str               # concatenated raw tool output (debug)

    # ── Extraction outputs
    extracted_contexts: list[dict]   # {url, content_summary, key_points, ...}
    extraction_errors:  list[str]    # URLs that failed quality gate or errored

    # ── Writer output
    draft_report: str
    # Owned by node_writer's self-critique pass (see writer.py). register_score
    # is the writer's OWN pre-revision assessment (0-10, out of the same
    # register rubric the evaluator independently re-checks below) —
    # optional because older runs / a failed critique call leave it unset.
    # Default to None/False at initial-state construction time in pipeline.py.
    writer_register_score:   Optional[int]
    writer_register_revised: Optional[bool]

    # ── Evaluator output
    evaluation: dict   # relevance/coverage/synthesis/citation/recency/register scores + verdict

    # ── Control flow
    retry_count: int
    error_log:   list[str]


class DiscoveryOutput(BaseModel):
    """Expected JSON structure from the discovery agent (kept for backward compatibility)."""
    search_queries: list[str] = Field(
        description="2–4 refined search queries to find the most relevant papers",
        min_length=1,
    )
    papers: list[dict] = Field(
        description="List of papers with keys: title, url, snippet, relevance_note"
    )


class ExtractionOutput(BaseModel):
    url:              str
    content_summary:  str  = Field(description="300-500 word summary focused on the research topic")
    key_points:       list[str] = Field(description="5-8 complete-sentence key findings")
    methodology:      str  = Field(description="Research methodology used")
    citations:        list[str] = Field(description="In-text citations or referenced works found")
    relevance_to_topic: str = Field(description="How this paper relates to the research topic")


class EvaluationOutput(BaseModel):
    relevance_score:        int   = Field(ge=0, le=10)
    coverage_score:         int   = Field(ge=0, le=10)
    synthesis_score:        int   = Field(ge=0, le=10)
    citation_score:         int   = Field(ge=0, le=10)
    recency_score:          int   = Field(ge=0, le=10,
        description="How recent are the papers? Penalise if most are older than 3 years")
    register_score:         int   = Field(ge=0, le=10,
        description=(
            "Independent evaluator judgement of academic-register adherence in "
            "the FINAL report text — no first person, no contractions, no "
            "rhetorical questions/exclamation marks, precise (not vague) "
            "hedging. Judged directly from the report, not deferred to the "
            "writer's own self-critique score."
        ))
    overall_score:          float
    strengths:              list[str]
    weaknesses:              list[str]
    improvement_suggestions: list[str]
    verdict:                str