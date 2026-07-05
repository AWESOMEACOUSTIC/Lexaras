import streamlit as st
from ui_impl.controller import score_css_class

_STAGES = [
    ("🔍", "Discovery",   "Generating queries · Searching the web"),
    ("📖", "Extraction",  "Reading papers · Pulling key context"),
    ("✍️",  "Writing",     "Synthesising report across all sources"),
    ("🧪", "Evaluation",  "Scoring relevance, coverage & quality"),
]

def render_stages(placeholder, active: int = -1, done: int = 0, failed: bool = False) -> None:
    """Render the pipeline stage tracker as clean step rows with connecting lines."""
    parts: list[str] = ['<div class="stage-wrap">']
    for i, (icon, name, sub) in enumerate(_STAGES):
        if i < done:
            css, status = "s-done", "Complete"
        elif i == active and failed:
            css, status = "s-error", "Error"
        elif i == active:
            css, status = "s-active", "Running…"
        else:
            css, status = "s-idle", "Waiting"
        parts.append(f"""
        <div class="stage-card {css}">
            <div class="stage-icon">{icon}</div>
            <div class="stage-text">
                <div class="s-name">{name}</div>
                <div class="s-sub">{status if i <= active or i < done else sub}</div>
            </div>
        </div>
        """)
    parts.append("</div>")
    placeholder.markdown("".join(parts), unsafe_allow_html=True)


def render_metrics(placeholder, r: dict, elapsed: float) -> None:
    """Render the run stats as a clean 2×2 metric grid with source split and elapsed time."""
    papers   = len(r.get("discovered_papers", []))
    num_scholar = len(r.get("scholar_papers", []))
    num_web = len(r.get("web_papers", []))
    extracted = len(r.get("extracted_contexts", []))
    words    = len(r.get("draft_report", "").split())
    score    = r.get("evaluation", {}).get("overall_score", 0)
    sc_cls   = score_css_class(float(score)) if score else "c-muted"

    # Source split percentages
    scholar_pct = (num_scholar / max(1, papers)) * 100
    web_pct = (num_web / max(1, papers)) * 100

    placeholder.markdown(f"""
    <div class="metric-grid">
        <div class="metric-pill">
            <div class="mp-label">Papers found</div>
            <div class="mp-value c-purple">{papers}</div>
            <div class="mp-sub">{num_scholar} scholar · {num_web} web</div>
        </div>
        <div class="metric-pill">
            <div class="mp-label">Extracted</div>
            <div class="mp-value">{extracted}</div>
        </div>
        <div class="metric-pill">
            <div class="mp-label">Report words</div>
            <div class="mp-value">{words:,}</div>
        </div>
        <div class="metric-pill">
            <div class="mp-label">Overall score</div>
            <div class="mp-value {sc_cls}">{score if score else "—"}</div>
        </div>
    </div>

    <!-- Source split bar -->
    <div class="source-split-inline">
        <div class="source-split-label">Scholar {num_scholar}</div>
        <div class="source-split-bar">
            <div class="source-split-fill-scholar" style="width: {scholar_pct}%;"></div>
            <div class="source-split-fill-web" style="width: {web_pct}%;"></div>
        </div>
        <div class="source-split-label">Web {num_web}</div>
    </div>

    <!-- Elapsed time -->
    <div class="elapsed-row">
        <div class="elapsed-label">Elapsed</div>
        <div class="elapsed-value">{elapsed:.1f}s</div>
    </div>
    """, unsafe_allow_html=True)
