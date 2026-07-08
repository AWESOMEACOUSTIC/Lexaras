import logging
import re
import requests
import textwrap
from typing import Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# Constants
MAX_SNIPPET_CHARS   = 500
MAX_SCRAPED_CHARS   = 4_000
MAX_PDF_CHARS       = 6_000
SCRAPE_TIMEOUT_SEC  = 12
SERPAPI_TIMEOUT_SEC = 15
WEB_MAX_RESULTS     = 5    # per Tavily call in default mode

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_session = requests.Session()
_session.headers.update(_HTTP_HEADERS)

def _trim_to_sentence(text: str, max_chars: int) -> str:
    """
    Trim text to `max_chars` but break cleanly at the last sentence boundary
    so the LLM doesn't receive a mid-sentence cut which hurts comprehension.
    """
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    # Walk back to the last sentence-ending punctuation
    last_boundary = max(
        truncated.rfind(". "),
        truncated.rfind(".\n"),
        truncated.rfind("! "),
        truncated.rfind("? "),
    )
    if last_boundary > max_chars // 2:          # only use if we found something reasonable
        return truncated[: last_boundary + 1].strip()
    return truncated.strip() + "…"


def _clean_html(raw_html: str) -> str:
    """
    Strip boilerplate tags, collapse whitespace, and return readable plain text.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    # Remove structural noise
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "aside", "header",
         "noscript", "iframe", "form", "button", "svg", "figure"]
    ):
        tag.decompose()

    # Prefer <article> or <main> if present — usually the real content
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)

    # Collapse 3+ consecutive newlines into two
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


class RedirectDriftError(ValueError):
    """
    Raised when a fetch resolves to a generic homepage/root path after
    following redirects, despite the requested URL targeting a specific
    page — a strong signal the real content was never reached.

    Kept as its own exception type (rather than a bare ValueError) so
    callers can catch it specifically and tag the failure distinctly,
    instead of it falling into a generic "unexpected error" bucket.
    """
    pass


_network_retry = retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)

def _is_redirect_drift(original_url: str, final_url: str) -> bool:
    """
    Check if the final URL is a generic homepage/root path but the original URL
    was targeting a specific path, indicating the link was redirected to a homepage.
    """
    orig_parsed = urlparse(original_url)
    final_parsed = urlparse(final_url)
    
    if original_url == final_url:
        return False
        
    orig_path = orig_parsed.path.strip("/")
    final_path = final_parsed.path.strip("/")
    
    # Generic homepage/index paths
    generic_paths = {"", "index.html", "index.htm", "home", "welcome", "main"}
    
    if orig_path not in generic_paths and final_path in generic_paths:
        return True
        
    return False


@_network_retry
def _fetch_with_retry(url: str) -> requests.Response:
    """Isolated so tenacity can wrap just the network call."""
    resp = _session.get(url, timeout=SCRAPE_TIMEOUT_SEC, allow_redirects=True)
    resp.raise_for_status()
    
    if resp.history:
        if _is_redirect_drift(url, resp.url):
            raise RedirectDriftError(f"{url} redirected to homepage {resp.url}")
            
    return resp


def _result_envelope(
    index: int,
    title: str,
    url: str,
    snippet: str,
    source: str,                    # "scholar" | "web"
    publication_year: Optional[int],
    authors: Optional[str] = None,
    citation_count: Optional[int] = None,
) -> str:
    """
    Single consistent text block for every search result, regardless of source.
    Downstream agents parse this uniformly — they never need to know whether
    the result came from SerpApi or Tavily.
    """
    year_str    = str(publication_year) if publication_year else "Unknown"
    authors_str = authors if authors else "Unknown"
    cite_str    = str(citation_count) if citation_count is not None else "N/A"

    return textwrap.dedent(f"""
    [{index}] {title}
        Source       : {source.upper()}
        URL          : {url}
        Year         : {year_str}
        Authors      : {authors_str}
        Citations    : {cite_str}
        Snippet      : {snippet}
    """).strip()


# ── Raw-content quality gate ─────────────────────────────────────────────────
#
# This runs on the ACTUAL scraped/extracted text, before it ever reaches an
# LLM to summarize. The prior gate (see extraction.py's original
# `_looks_like_wall`) only checked the LLM's own summary — which means a wall
# page that gets paraphrased into plausible-sounding prose ("the publisher
# requires an institutional subscription to view this content") can slip past
# a check for literal phrases like "sign in to read", because the model never
# reused those exact words. Checking the raw text closes that gap: the raw
# HTML/PDF text of an access wall reliably DOES contain these phrases verbatim,
# regardless of what the model later says about it.

CONTENT_QUALITY_FLAG_PREFIX = "CONTENT_QUALITY_FLAG:"

_WALL_MARKERS = (
    "sign in to read", "purchase access", "institutional login",
    "buy this article", "access through your institution",
    "we use cookies", "cookie consent", "accept all cookies",
    "subscribe to continue", "javascript is required",
    "enable javascript", "verify you are human", "log in to continue",
    "purchase pdf", "captcha", "checking your browser",
)

# Structural sanity thresholds. Deliberately lenient — the goal is to catch
# obvious garbage (nav-menu dumps, cookie banners, link lists) without
# rejecting legitimate dense academic prose, which can have long sentences
# and technical vocabulary that looks unusual to a naive heuristic.
_MIN_SENTENCES            = 4
_MIN_UNIQUE_WORD_RATIO    = 0.28   # unique words / total words
_MIN_AVG_WORDS_PER_SENTENCE = 3.0  # catches "Home | About | Contact" style dumps


def _looks_like_wall(text: str) -> Optional[str]:
    """
    Cheap substring check for access-wall / consent-wall language.
    Returns a reason string (naming the matched phrases) if flagged, else None.
    """
    lowered = text.lower()
    hits = [m for m in _WALL_MARKERS if m in lowered]
    if len(hits) >= 2 or (len(hits) >= 1 and len(text) < 2000):
        return f"matched wall phrase(s): {', '.join(hits[:3])}"
    return None


def _structural_quality_ok(text: str) -> Optional[str]:
    """
    Cheap prose-shape check. Returns a reason string if the text doesn't look
    like real article prose (e.g. a nav-menu/link-list dump, a mostly-empty
    page, or heavily repeated boilerplate), else None.
    """
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    words = re.findall(r"[A-Za-z']+", text.lower())

    if len(sentences) < _MIN_SENTENCES:
        return f"only {len(sentences)} sentence(s) detected (expected at least {_MIN_SENTENCES})"

    if not words:
        return "no words detected after cleaning"

    unique_ratio = len(set(words)) / len(words)
    if unique_ratio < _MIN_UNIQUE_WORD_RATIO:
        return f"unique-word ratio {unique_ratio:.2f} is below {_MIN_UNIQUE_WORD_RATIO} (repetitive boilerplate)"

    avg_words_per_sentence = len(words) / len(sentences)
    if avg_words_per_sentence < _MIN_AVG_WORDS_PER_SENTENCE:
        return (
            f"average {avg_words_per_sentence:.1f} words/sentence is below "
            f"{_MIN_AVG_WORDS_PER_SENTENCE} (looks like a link/nav list, not prose)"
        )

    return None


def _quality_gate(text: str) -> Optional[str]:
    """
    Runs the wall-marker check and the structural sanity check, in that
    order (cheapest first). Returns the first failure reason found, or None
    if the text passes both.
    """
    wall_reason = _looks_like_wall(text)
    if wall_reason:
        return f"ACCESS_WALL_SUSPECTED — {wall_reason}"

    structural_reason = _structural_quality_ok(text)
    if structural_reason:
        return f"LOW_QUALITY_TEXT — {structural_reason}"

    return None


def _gate_and_prefix(formatted_result: str) -> str:
    """
    Applies the quality gate to an already-formatted tool result string and,
    if it fails, prepends a machine-readable flag line. Callers (scrape_url,
    and by extension anything that wraps its output such as the PDF-delegate
    branch) should route their final return value through this so the flag
    is visible both to the calling LLM in-context and to a deterministic
    downstream check (see extraction.py's raw ToolMessage scan).
    """
    reason = _quality_gate(formatted_result)
    if reason:
        logger.warning("[QualityGate] Flagged content: %s", reason)
        return f"{CONTENT_QUALITY_FLAG_PREFIX} {reason}\n\n{formatted_result}"
    return formatted_result