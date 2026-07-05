import streamlit as st
from ui_impl.controller import md_to_html, score_color, score_bar_html

def render_report_tab(r: dict, topic_label: str) -> None:
    draft = r.get("draft_report", "")
    if not draft or draft.startswith("[WRITER_ERROR]"):
        st.markdown('<div class="err-box">The writer agent did not produce a report. See the Debug tab for details.</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="report-body">{md_to_html(draft)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.download_button(
            label="⬇  Download as Markdown",
            data=draft,
            file_name=f"lexaras_{topic_label[:40].replace(' ','_')}.md",
            mime="text/markdown",
        )

def render_sources_tab(r: dict) -> None:
    papers = r.get("discovered_papers", [])
    contexts = r.get("extracted_contexts", [])

    if not papers:
        st.markdown('<div class="err-box">No papers were discovered.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="sec-label">{len(papers)} Papers Discovered</div>', unsafe_allow_html=True)
        for p in papers:
            source_badge = '<span class="badge badge-scholar">Scholar</span>' if p.get("source") == "scholar" else '<span class="badge badge-web">Web</span>'
            year_badge = f'<span class="badge badge-year">{p.get("publication_year")}</span>' if p.get("publication_year") else ''
            st.markdown(f"""
            <div class="paper-card">
                <div class="pc-title">{p.get("title","Untitled")}</div>
                <div class="pc-meta">
                    {source_badge}
                    {year_badge}
                </div>
                <div class="pc-authors">{p.get("authors","")}</div>
                <div class="pc-url"><a href="{p.get("url","#")}" target="_blank">{p.get("url","")}</a></div>
                <div class="pc-note">{p.get("relevance_note","")}</div>
            </div>
            """, unsafe_allow_html=True)

    if contexts:
        st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)
        st.markdown(f'<div class="sec-label">{len(contexts)} Papers Extracted</div>', unsafe_allow_html=True)
        for ctx in contexts:
            url = ctx.get("url", "—")
            key_points = ctx.get("key_points", [])
            with st.expander(f"📄  {url[:75]}{'…' if len(url) > 75 else ''}"):
                st.markdown(f'<div class="extract-url">{url}</div>', unsafe_allow_html=True)

                if ctx.get("content_summary"):
                    st.markdown(
                        f'<div class="extract-summary">{ctx["content_summary"]}</div>',
                        unsafe_allow_html=True,
                    )
                if key_points:
                    kp_items = "".join(f'<li><span class="kp-bullet">›</span> <div>{kp}</div></li>' for kp in key_points)
                    st.markdown(
                        f'<ul class="kp-list">{kp_items}</ul>',
                        unsafe_allow_html=True,
                    )
                if ctx.get("methodology"):
                    st.markdown(
                        f'<div class="extract-methodology"><strong>Methodology:</strong> {ctx["methodology"]}</div>',
                        unsafe_allow_html=True,
                    )

def render_evaluation_tab(r: dict) -> None:
    ev = r.get("evaluation", {})
    if not ev or ev.get("error"):
        st.markdown(
            f'<div class="err-box">Evaluation did not complete.<br>{ev.get("error","")}</div>',
            unsafe_allow_html=True,
        )
    else:
        overall = float(ev.get("overall_score", 0))
        verdict = ev.get("verdict", "")
        ring_color = score_color(overall)

        # Overall score ring + verdict
        st.markdown(f"""
        <div class="score-hero">
            <div class="score-ring-outer" style="background: conic-gradient({ring_color} {overall/10*360}deg, #1e1e30 0deg);">
                <div class="score-ring-inner" style="color:{ring_color};">
                    {overall:.1f}
                </div>
            </div>
            <div class="score-verdict-block">
                <div class="score-label">Overall Score</div>
                <div class="score-text">{verdict}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Dimension score bars
        st.markdown('<div class="sec-label" style="margin-top:0.5rem;">Dimension Scores</div>', unsafe_allow_html=True)
        dims = [
            ("Relevance",  ev.get("relevance_score",  0)),
            ("Coverage",   ev.get("coverage_score",   0)),
            ("Synthesis",  ev.get("synthesis_score",  0)),
            ("Citations",  ev.get("citation_score",   0)),
        ]
        bars_html = "".join(score_bar_html(label, val) for label, val in dims)
        st.markdown(
            f'<div class="score-bars-wrap">{bars_html}</div>',
            unsafe_allow_html=True,
        )

        # Strengths / Weaknesses / Suggestions
        st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)
        col_s, col_w = st.columns(2, gap="medium")

        with col_s:
            st.markdown('<div class="sec-label">Strengths</div>', unsafe_allow_html=True)
            items = "".join(
                f'<li><span class="fb-icon" style="color:#4ade80;">✓</span> <div>{s}</div></li>'
                for s in ev.get("strengths", [])
            )
            st.markdown(f'<ul class="fb-list">{items}</ul>', unsafe_allow_html=True)

        with col_w:
            st.markdown('<div class="sec-label">Weaknesses</div>', unsafe_allow_html=True)
            items = "".join(
                f'<li><span class="fb-icon" style="color:#f87171;">✗</span> <div>{w}</div></li>'
                for w in ev.get("weaknesses", [])
            )
            st.markdown(f'<ul class="fb-list">{items}</ul>', unsafe_allow_html=True)

        suggestions = ev.get("improvement_suggestions", [])
        if suggestions:
            st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)
            st.markdown('<div class="sec-label">Improvement Suggestions</div>', unsafe_allow_html=True)
            items = "".join(
                f'<li><span class="fb-icon" style="color:#8b83ff;">→</span> <div>{s}</div></li>'
                for s in suggestions
            )
            st.markdown(f'<ul class="fb-list">{items}</ul>', unsafe_allow_html=True)

def render_debug_tab(r: dict) -> None:
    st.markdown('<div class="sec-label">Search Queries Generated</div>', unsafe_allow_html=True)
    queries = r.get("search_queries", [])
    if queries:
        for i, q in enumerate(queries, 1):
            # Parse out source tag if encoded in query string (from old _collect_scholar_papers)
            source_tag = ""
            if "]" in q and "[" in q:
                # E.g. "transformer architecture [2024]"
                # Just render exactly what we fired.
                pass

            st.markdown(f"""
            <div class="query-pill">
                <div class="query-index">Q{i}</div>
                <div>{q}</div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#404068; font-size:0.84rem;">None recorded.</div>', unsafe_allow_html=True)

    retry_count = r.get("retry_count", 0)
    if retry_count:
        st.markdown(f"""
        <div class="warn-chip" style="margin-top:0.6rem;">
            ↻ Discovery retried {retry_count} time(s)
        </div>
        """, unsafe_allow_html=True)

    errors = r.get("extraction_errors", [])
    error_log = r.get("error_log", [])
    if errors or error_log:
        st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)
        st.markdown('<div class="sec-label">Errors & Warnings</div>', unsafe_allow_html=True)
        for e in errors:
            st.markdown(f'<div class="err-box" style="margin-bottom:0.4rem;">Extraction: {e}</div>', unsafe_allow_html=True)
        for e in error_log:
            st.markdown(f'<div class="err-box" style="margin-bottom:0.4rem;">Pipeline: {e}</div>', unsafe_allow_html=True)

    st.markdown('<hr class="lex-hr">', unsafe_allow_html=True)
    with st.expander("Raw discovery output"):
        st.text(r.get("discovery_raw", "—"))
