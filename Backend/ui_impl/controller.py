import os
import sys
import re
import html as _html

def md_to_html(text: str) -> str:
    """
    Minimal Markdown → HTML for headings, bullets, bold, inline code, and URLs.
    Avoids adding a `markdown` package dependency while keeping the
    report body correctly styled inside the custom .report-body <div>.
    """
    lines = text.split("\n")
    out: list[str] = []
    in_ul = False

    for raw in lines:
        s = _html.escape(raw)
        if s.startswith("### "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h3>{s[4:]}</h3>")
        elif s.startswith("## "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("# "):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<h1>{s[2:]}</h1>")
        elif s.startswith("- ") or s.startswith("* "):
            if not in_ul: out.append("<ul>"); in_ul = True
            out.append(f"<li>{s[2:]}</li>")
        elif s.startswith("---") or s.startswith("***"):
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("<hr>")
        elif s.strip() == "":
            if in_ul: out.append("</ul>"); in_ul = False
            out.append("<br>")
        else:
            if in_ul: out.append("</ul>"); in_ul = False
            out.append(f"<p>{s}</p>")

    if in_ul:
        out.append("</ul>")

    joined = "\n".join(out)
    joined = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", joined)
    joined = re.sub(r"`(.+?)`", r"<code>\1</code>", joined)
    joined = re.sub(
        r"(https?://[^\s<>\"']+)",
        r'<a href="\1" target="_blank">\1</a>',
        joined,
    )
    return joined


def score_color(score: float) -> str:
    if score >= 7.5: return "#22c55e"
    if score >= 5.0: return "#f59e0b"
    return "#ef4444"


def score_css_class(score: float) -> str:
    if score >= 7.5: return "c-green"
    if score >= 5.0: return "c-amber"
    return "c-red"


def score_bar_html(label: str, value: int, max_val: int = 10) -> str:
    pct = (value / max_val) * 100
    color = score_color(value)
    return f"""
    <div class="score-bar-row">
        <div class="sbr-label"><span>{label}</span><span>{value}/{max_val}</span></div>
        <div class="score-bar-bg">
            <div class="score-bar-fill" style="width:{pct}%; background:{color};"></div>
        </div>
    </div>
    """


def run_pipeline(topic: str) -> dict:
    """
    Runner wrapper around agents.run_research().
    sys.path injection ensures the import works from any working directory.
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from agents import run_research
    return run_research(topic)
