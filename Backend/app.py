"""
app.py — Lexaras Research Platform UI
----------------------------------------
Streamlit frontend for the Lexaras multi-agent research pipeline.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import sys
import os
import time

import streamlit as st

# Ensure Backend/ directory is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from ui_impl.styles import load_styles
from ui_impl.components import render_stages, render_metrics
from ui_impl.tabs import render_report_tab, render_sources_tab, render_evaluation_tab, render_debug_tab
from ui_impl.controller import run_pipeline

# ── Page config — must be the first Streamlit call
st.set_page_config(
    page_title="Lexaras",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Apply CSS styling
load_styles()

# ── Session state initialisation
_DEFAULTS = {
    "results": None,       # Final AgentState dict
    "error": None,         # Pipeline-level exception string
    "topic": "",           # Last submitted topic
    "elapsed": 0.0,        # Wall-clock seconds
    "stage": -1,           # Active stage index (-1 = idle)
    "all_done": False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Header
st.markdown("""
<div style="display:flex; align-items:baseline; gap:0; padding-bottom:1.6rem;">
    <span class="lex-wordmark">◈ Lex<span>aras</span></span>
    <span class="lex-tagline">research intelligence</span>
</div>
""", unsafe_allow_html=True)
st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)

# ── Two-column split
left, right = st.columns([5, 8], gap="large")

# ── LEFT PANEL (Inputs and Controls)
with left:
    st.markdown('<div class="sec-label">Research Topic</div>', unsafe_allow_html=True)
    topic_input = st.text_input(
        label="topic",
        placeholder="e.g. CRISPR gene editing in oncology",
        label_visibility="collapsed",
        key="topic_field",
    )
    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
    run_btn = st.button("Run Research  →", use_container_width=True)

    st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Pipeline</div>', unsafe_allow_html=True)
    stages_slot = st.empty()
    render_stages(stages_slot)

    st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)

    st.markdown('<div class="sec-label">Run Stats</div>', unsafe_allow_html=True)
    metrics_slot = st.empty()

    if st.session_state.results:
        render_metrics(metrics_slot, st.session_state.results, st.session_state.elapsed)
    else:
        # Render empty stats placeholder
        metrics_slot.markdown("""
        <div class="metric-grid">
            <div class="metric-pill"><div class="mp-label">Papers found</div><div class="mp-value" style="color:#2a2a40;">—</div></div>
            <div class="metric-pill"><div class="mp-label">Extracted</div><div class="mp-value" style="color:#2a2a40;">—</div></div>
            <div class="metric-pill"><div class="mp-label">Report words</div><div class="mp-value" style="color:#2a2a40;">—</div></div>
            <div class="metric-pill"><div class="mp-label">Overall score</div><div class="mp-value" style="color:#2a2a40;">—</div></div>
        </div>
        <div class="metric-pill" style="margin-top:0.5rem;">
            <div class="mp-label">Elapsed time</div>
            <div class="mp-value" style="color:#2a2a40;">—</div>
        </div>
        """, unsafe_allow_html=True)

# ── RIGHT PANEL (Output Results)
with right:
    if run_btn:
        topic = topic_input.strip()
        if not topic:
            st.markdown('<div class="err-box">⚠ Please enter a research topic before running.</div>', unsafe_allow_html=True)
        else:
            st.session_state.results = None
            st.session_state.error = None
            st.session_state.topic = topic
            st.session_state.all_done = False

            progress_slot = st.empty()
            try:
                t0 = time.perf_counter()
                stages_list = [
                    "Searching the web for relevant academic sources…",
                    "Reading and extracting content from each paper…",
                    "Synthesising findings into a structured report…",
                    "Evaluating report quality and scoring the pipeline…",
                ]
                for stage_idx, status_msg in enumerate(stages_list):
                    render_stages(stages_slot, active=stage_idx, done=stage_idx)
                    with progress_slot.container():
                        with st.spinner(status_msg):
                            if stage_idx == len(stages_list) - 1:
                                results = run_pipeline(topic)
                            else:
                                time.sleep(0.3)

                elapsed = time.perf_counter() - t0
                st.session_state.results = results
                st.session_state.elapsed = elapsed
                st.session_state.all_done = True

                render_stages(stages_slot, active=-1, done=len(stages_list))
                render_metrics(metrics_slot, results, elapsed)
                progress_slot.empty()
            except Exception as exc:
                st.session_state.error = str(exc)
                st.session_state.results = None
                render_stages(stages_slot, active=stage_idx, failed=True)
                progress_slot.empty()

    if st.session_state.error:
        st.markdown(f"""
        <div class="err-box">
            <strong>Pipeline error</strong><br><br>
            {st.session_state.error}<br><br>
            Check your <code>.env</code> keys and that all dependencies are installed,
            then try again.
        </div>
        """, unsafe_allow_html=True)
    elif st.session_state.results:
        r = st.session_state.results
        topic_label = st.session_state.topic
        errors = r.get("extraction_errors", [])

        st.markdown(f"""
        <div style="margin-bottom:1.2rem;">
            <div class="sec-label" style="margin-bottom:0.2rem;">Research output for</div>
            <div style="font-size:1.15rem; font-weight:700; color:#e8e8f8;">
                {topic_label}
            </div>
        </div>
        """, unsafe_allow_html=True)

        if errors:
            st.markdown(
                f'<div class="warn-chip">⚠ {len(errors)} paper(s) failed to extract</div>',
                unsafe_allow_html=True,
            )

        tab_report, tab_papers, tab_eval, tab_debug = st.tabs([
            "📄 Report",
            "📚 Sources",
            "🧪 Evaluation",
            "🔧 Debug",
        ])

        with tab_report:
            render_report_tab(r, topic_label)
        with tab_papers:
            render_sources_tab(r)
        with tab_eval:
            render_evaluation_tab(r)
        with tab_debug:
            render_debug_tab(r)
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="es-icon">◈</div>
            <div class="es-title">Ready to research</div>
            <div class="es-body">
                Enter any academic or technical topic on the left.<br>
                Lexaras will discover papers, extract findings,<br>
                write a structured report, and score it — end to end.
            </div>
        </div>
        """, unsafe_allow_html=True)