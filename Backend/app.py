"""
app.py — Lexaras Research Platform UI
----------------------------------------
Streamlit frontend for the Lexaras multi-agent research pipeline.

Run with:
    streamlit run app.py

Sits inside Backend/ alongside pipeline.py, agents.py, and tools.py.
No extra dependencies beyond what's already in requirements.txt — just add:
    streamlit>=1.35.0
"""

import sys
import time
import streamlit as st

# ── Page config must be the very first Streamlit call ──────────────────────
st.set_page_config(
    page_title="Lexaras",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS — dark theme, minimal, modern ───────────────────────────────
st.markdown("""
<style>
/* ── Base & reset ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #0a0a0f !important;
    color: #e2e2e8 !important;
    font-family: 'Inter', sans-serif !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] {
    display: none !important;
}

/* Block container — tighten the default padding */
[data-testid="block-container"] {
    padding: 2.5rem 3rem 4rem 3rem !important;
    max-width: 1100px !important;
    margin: 0 auto !important;
}

/* ── Typography ── */
h1, h2, h3, h4 { font-family: 'Inter', sans-serif !important; font-weight: 600 !important; }

/* ── Input ── */
[data-testid="stTextInput"] input {
    background: #13131a !important;
    border: 1px solid #2a2a3a !important;
    border-radius: 10px !important;
    color: #e2e2e8 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 1rem !important;
    padding: 0.75rem 1rem !important;
    transition: border-color 0.2s ease !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: #6c63ff !important;
    box-shadow: 0 0 0 3px rgba(108, 99, 255, 0.15) !important;
    outline: none !important;
}
[data-testid="stTextInput"] label {
    color: #8888aa !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    font-weight: 500 !important;
}

/* ── Primary button ── */
[data-testid="stButton"] > button {
    background: #6c63ff !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.65rem 2rem !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    transition: background 0.2s ease, transform 0.1s ease !important;
    cursor: pointer !important;
}
[data-testid="stButton"] > button:hover {
    background: #7c74ff !important;
    transform: translateY(-1px) !important;
}
[data-testid="stButton"] > button:active {
    transform: translateY(0px) !important;
}

/* ── Tab bar ── */
[data-testid="stTabs"] [role="tablist"] {
    background: #13131a !important;
    border-radius: 10px !important;
    padding: 4px !important;
    border: 1px solid #1e1e2e !important;
    gap: 2px !important;
}
[data-testid="stTabs"] [role="tab"] {
    background: transparent !important;
    color: #6666aa !important;
    border-radius: 7px !important;
    padding: 0.45rem 1.1rem !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    border: none !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background: #6c63ff !important;
    color: #ffffff !important;
}
[data-testid="stTabs"] [role="tab"]:hover:not([aria-selected="true"]) {
    color: #c0c0dd !important;
    background: #1e1e2e !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #13131a !important;
    border: 1px solid #1e1e2e !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #8888aa !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

/* ── Markdown content inside report areas ── */
.report-body {
    background: #13131a;
    border: 1px solid #1e1e2e;
    border-radius: 12px;
    padding: 2rem 2.2rem;
    font-size: 0.95rem;
    line-height: 1.8;
    color: #d0d0e0;
}
.report-body h1, .report-body h2, .report-body h3 {
    color: #ffffff;
    margin-top: 1.4em;
    margin-bottom: 0.5em;
}
.report-body strong { color: #c8c4ff; }
.report-body a { color: #6c63ff; text-decoration: none; }
.report-body a:hover { text-decoration: underline; }
.report-body ul, .report-body ol { padding-left: 1.4em; }
.report-body li { margin-bottom: 0.35em; }
.report-body code {
    background: #1e1e2e;
    padding: 0.15em 0.4em;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85em;
    color: #a0f0c0;
}

/* ── Stage card ── */
.stage-card {
    background: #13131a;
    border: 1px solid #1e1e2e;
    border-radius: 12px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 0.6rem;
    display: flex;
    align-items: center;
    gap: 0.9rem;
    transition: border-color 0.3s ease;
}
.stage-card.active  { border-color: #6c63ff; }
.stage-card.done    { border-color: #22c55e; }
.stage-card.idle    { border-color: #1e1e2e; }
.stage-icon { font-size: 1.1rem; width: 1.6rem; text-align: center; }
.stage-label { font-size: 0.88rem; font-weight: 500; color: #c0c0d8; }
.stage-status { font-size: 0.78rem; color: #6666aa; margin-top: 0.15rem; }

/* ── Metric pill ── */
.metric-row {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 1.5rem 0 0.5rem 0;
}
.metric-pill {
    background: #13131a;
    border: 1px solid #1e1e2e;
    border-radius: 8px;
    padding: 0.65rem 1.1rem;
    flex: 1;
    min-width: 130px;
}
.metric-pill .m-label {
    font-size: 0.72rem;
    color: #6666aa;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 500;
}
.metric-pill .m-value {
    font-size: 1.3rem;
    font-weight: 600;
    color: #e2e2e8;
    margin-top: 0.2rem;
}
.metric-pill .m-value.accent { color: #6c63ff; }
.metric-pill .m-value.green  { color: #22c55e; }
.metric-pill .m-value.amber  { color: #f59e0b; }

/* ── Divider ── */
.lex-divider {
    border: none;
    border-top: 1px solid #1e1e2e;
    margin: 1.8rem 0;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 4rem 2rem;
    color: #444466;
}
.empty-state .big-icon { font-size: 3rem; margin-bottom: 1rem; }
.empty-state p { font-size: 0.9rem; line-height: 1.6; }

/* ── Error box ── */
.error-box {
    background: #1a0f0f;
    border: 1px solid #5a1a1a;
    border-radius: 10px;
    padding: 1rem 1.4rem;
    color: #ff8888;
    font-size: 0.88rem;
}

/* ── Spinner override ── */
[data-testid="stSpinner"] { color: #6c63ff !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0a0a0f; }
::-webkit-scrollbar-thumb { background: #2a2a3a; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #3a3a55; }
</style>
""", unsafe_allow_html=True)


# ── Session state initialisation ───────────────────────────────────────────
def _init_state():
    defaults = {
        "running": False,
        "results": None,
        "error": None,
        "topic": "",
        "elapsed": 0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ── Pipeline runner (cached on topic) ─────────────────────────────────────
@st.cache_data(show_spinner=False)
def _run_pipeline(topic: str) -> dict:
    """
    Thin wrapper so Streamlit only re-runs the pipeline when the topic changes.
    Adds `sys.path` manipulation so the import works whether app.py is run
    from the project root or the Backend/ directory.
    """
    import os, sys
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from pipeline import research_pipeline
    return research_pipeline(topic)


# ══════════════════════════════════════════════════════════════════════════
#  HELPER — lightweight markdown → HTML for the report body
#  (avoids Streamlit's st.markdown losing dark-theme styles inside divs)
# ══════════════════════════════════════════════════════════════════════════
def _md_to_html(text: str) -> str:
    """
    Minimal markdown → HTML conversion for headings, bold, bullets, and links.
    Keeps us from needing an extra `markdown` package dependency while
    ensuring the report renders correctly inside the styled <div>.
    """
    import re, html as html_lib

    lines = text.split("\n")
    out = []
    in_ul = False

    for line in lines:
        # Escape HTML entities first
        safe = html_lib.escape(line)

        # Headings
        if safe.startswith("### "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h3>{safe[4:]}</h3>")
        elif safe.startswith("## "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h2>{safe[3:]}</h2>")
        elif safe.startswith("# "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h1>{safe[2:]}</h1>")
        # Bullets
        elif safe.startswith("- ") or safe.startswith("* "):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{safe[2:]}</li>")
        # Blank line
        elif safe.strip() == "":
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("<br>")
        # Normal paragraph line
        else:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<p>{safe}</p>")

    if in_ul:
        out.append("</ul>")

    joined = "\n".join(out)

    # Inline bold **text**
    joined = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", joined)
    # Inline code `text`
    joined = re.sub(r"`(.+?)`", r"<code>\1</code>", joined)
    # URLs (after escaping, http stays http — &amp; would break, but URLs don't have &)
    joined = re.sub(
        r"(https?://[^\s&lt;&quot;&apos;<>]+)",
        r'<a href="\1" target="_blank">\1</a>',
        joined,
    )

    return joined

# ══════════════════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════════════════
col_logo, col_spacer = st.columns([1, 3])
with col_logo:
    st.markdown("""
    <div style="padding: 0.2rem 0 1.6rem 0;">
        <span style="font-size:1.6rem; font-weight:700; letter-spacing:-0.02em; color:#ffffff;">
            ◈ Lexaras
        </span>
        <span style="font-size:0.75rem; color:#444466; margin-left:0.6rem; font-weight:400;">
            research intelligence
        </span>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<hr class="lex-divider">', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN LAYOUT — two columns: left input/status, right output
# ══════════════════════════════════════════════════════════════════════════
left, right = st.columns([1, 2], gap="large")


# ── LEFT PANEL ─────────────────────────────────────────────────────────────
with left:
    st.markdown("""
    <p style="font-size:0.72rem; color:#6666aa; text-transform:uppercase;
              letter-spacing:0.1em; font-weight:500; margin-bottom:0.3rem;">
        Research Topic
    </p>
    """, unsafe_allow_html=True)

    topic_input = st.text_input(
        label="topic",
        placeholder="e.g. transformer attention in protein folding",
        label_visibility="collapsed",
        key="topic_input_field",
    )

    st.markdown("<div style='height:0.6rem'></div>", unsafe_allow_html=True)

    run_clicked = st.button("Run Research  →", use_container_width=True)

    st.markdown('<hr class="lex-divider">', unsafe_allow_html=True)

    # ── Pipeline stages ──
    st.markdown("""
    <p style="font-size:0.72rem; color:#6666aa; text-transform:uppercase;
              letter-spacing:0.1em; font-weight:500; margin-bottom:0.8rem;">
        Pipeline
    </p>
    """, unsafe_allow_html=True)

    stages_placeholder = st.empty()

    def _render_stages(active_idx: int = -1, done_up_to: int = -1):
        stages = [
            ("🔍", "Discovery",  "Searching the web for sources"),
            ("📖", "Extraction", "Reading & extracting content"),
            ("✍️", "Writing",    "Synthesising the report"),
            ("🧪", "Evaluation", "Fact-checking & scoring"),
        ]
        html_parts = []
        for i, (icon, label, subtitle) in enumerate(stages):
            if i < done_up_to:
                css = "done"; status = "Complete"
            elif i == active_idx:
                css = "active"; status = "Running…"
            else:
                css = "idle"; status = "Waiting"
            html_parts.append(f"""
            <div class="stage-card {css}">
                <div class="stage-icon">{icon}</div>
                <div>
                    <div class="stage-label">{label}</div>
                    <div class="stage-status">{status}</div>
                </div>
            </div>
            """)
        stages_placeholder.markdown("".join(html_parts), unsafe_allow_html=True)

    # Initial idle render
    _render_stages()

    # ── Metrics (shown only after a run) ──
    metrics_placeholder = st.empty()

    if st.session_state.results:
        r = st.session_state.results
        words = len(r.get("writer_results", "").split())
        sources = r.get("writer_results", "").count("http")
        elapsed = st.session_state.elapsed

        metrics_placeholder.markdown(f"""
        <div class="metric-row">
            <div class="metric-pill">
                <div class="m-label">Words</div>
                <div class="m-value accent">{words:,}</div>
            </div>
            <div class="metric-pill">
                <div class="m-label">Sources</div>
                <div class="m-value">{sources}</div>
            </div>
            <div class="metric-pill">
                <div class="m-label">Time</div>
                <div class="m-value">{elapsed:.0f}s</div>
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── RIGHT PANEL ────────────────────────────────────────────────────────────
with right:

    # ── Handle button click ──
    if run_clicked:
        topic = topic_input.strip()
        if not topic:
            st.markdown("""
            <div class="error-box">
                ⚠ Please enter a research topic before running.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.session_state.results = None
            st.session_state.error = None
            st.session_state.topic = topic

            # Progress animation through stages
            progress_container = st.empty()

            try:
                t0 = time.perf_counter()

                # Stage 1 — Discovery
                _render_stages(active_idx=0, done_up_to=0)
                with progress_container.container():
                    with st.spinner("Searching the web for relevant sources…"):
                        # We drive one pipeline call; stages animate
                        # concurrently via the spinner UX
                        pass

                # Stage 2 — Extraction
                _render_stages(active_idx=1, done_up_to=1)
                with progress_container.container():
                    with st.spinner("Extracting content from sources…"):
                        pass

                # Stage 3 — Writing
                _render_stages(active_idx=2, done_up_to=2)
                with progress_container.container():
                    with st.spinner("Writing the research report…"):
                        pass

                # Stage 4 — Evaluating (run the actual pipeline here)
                _render_stages(active_idx=3, done_up_to=3)
                with progress_container.container():
                    with st.spinner("Running pipeline — this may take a minute…"):
                        results = _run_pipeline(topic)

                elapsed = time.perf_counter() - t0
                st.session_state.results = results
                st.session_state.elapsed = elapsed
                st.session_state.error = None

                _render_stages(active_idx=-1, done_up_to=4)  # all done
                progress_container.empty()

                # Refresh metrics panel
                r = results
                words = len(r.get("writer_results", "").split())
                sources = r.get("writer_results", "").count("http")
                metrics_placeholder.markdown(f"""
                <div class="metric-row">
                    <div class="metric-pill">
                        <div class="m-label">Words</div>
                        <div class="m-value accent">{words:,}</div>
                    </div>
                    <div class="metric-pill">
                        <div class="m-label">Sources</div>
                        <div class="m-value">{sources}</div>
                    </div>
                    <div class="metric-pill">
                        <div class="m-label">Time</div>
                        <div class="m-value">{elapsed:.0f}s</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            except Exception as exc:
                st.session_state.error = str(exc)
                st.session_state.results = None
                progress_container.empty()
                _render_stages()

    # ── Error state ──
    if st.session_state.error:
        st.markdown(f"""
        <div class="error-box">
            <strong>Pipeline error</strong><br>
            {st.session_state.error}
        </div>
        """, unsafe_allow_html=True)

    # ── Results ──
    elif st.session_state.results:
        r = st.session_state.results
        topic_display = st.session_state.topic

        st.markdown(f"""
        <p style="font-size:0.72rem; color:#6666aa; text-transform:uppercase;
                  letter-spacing:0.1em; font-weight:500; margin-bottom:0.2rem;">
            Results for
        </p>
        <p style="font-size:1.1rem; font-weight:600; color:#e2e2e8;
                  margin-bottom:1.2rem;">
            {topic_display}
        </p>
        """, unsafe_allow_html=True)

        tab_report, tab_critic, tab_raw = st.tabs(["Report", "Critic Review", "Raw Data"])

        # ── Tab 1: Report ──
        with tab_report:
            writer_md = r.get("writer_results", "No report generated.")
            st.markdown(
                f'<div class="report-body">{_md_to_html(writer_md)}</div>',
                unsafe_allow_html=True
            )
            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
            st.download_button(
                label="⬇ Download Report (.md)",
                data=writer_md,
                file_name=f"lexaras_{topic_display[:40].replace(' ', '_')}.md",
                mime="text/markdown",
            )

        # ── Tab 2: Critic Review ──
        with tab_critic:
            critic_md = r.get("critic_results", "No critic review generated.")
            st.markdown(
                f'<div class="report-body">{_md_to_html(critic_md)}</div>',
                unsafe_allow_html=True
            )

        # ── Tab 3: Raw Data ──
        with tab_raw:
            with st.expander("Search Results (raw agent output)"):
                st.text(r.get("search_results", "—"))
            with st.expander("Reader / Extraction Output"):
                st.text(r.get("reader_results", "—"))

    # ── Empty / idle state ──
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="big-icon">◈</div>
            <p>
                Enter a research topic on the left and hit <strong>Run Research</strong>.<br>
                Lexaras will search the web, read the sources, write a structured<br>
                report, and score it — automatically.
            </p>
        </div>
        """, unsafe_allow_html=True)


