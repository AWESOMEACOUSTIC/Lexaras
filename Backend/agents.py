"""
agents.py — Lexaras Research Platform
---------------------------------------
Exposes the multi-agent research pipeline and the public execution interface.
"""

from agents_impl.pipeline import pipeline, run_research
from agents_impl.state import (
    AgentState,
    PaperMeta,
    DiscoveryOutput,
    ExtractionOutput,
    EvaluationOutput,
)