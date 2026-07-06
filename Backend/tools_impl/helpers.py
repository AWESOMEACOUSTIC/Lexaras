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
            raise ValueError(f"Redirect drift detected: {url} redirected to homepage {resp.url}")
            
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
