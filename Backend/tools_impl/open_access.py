import logging
import requests
from difflib import SequenceMatcher
from urllib.parse import urlparse
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

# Reuse the main scraping session (spoofed browser User-Agent, retry/adapter
# config) so the reachability probe sees the same responses extraction will.
# Falls back to a locally-built browser-UA session if helpers isn't importable
# (e.g. import-order/circular concerns) — the probe still works, just without
# whatever extra adapter config helpers may add.
try:
    from tools_impl.helpers import _session as _probe_session
except Exception:  # pragma: no cover - defensive fallback
    _probe_session = requests.Session()
    _probe_session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    })

# Hosts where an OA link is essentially always genuinely fetchable.
KNOWN_OPEN_HOST_PATTERNS = (
    "arxiv.org",
    "ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "biorxiv.org",
    "medrxiv.org",
    "ssrn.com",
    "zenodo.org",
    "osf.io",
    "europepmc.org",
    "doaj.org",
    "plos.org",
    "frontiersin.org",
    "mdpi.com",
    "hal.science",
)

# Minimum title similarity for a resolver hit to count as the same paper.
_TITLE_MATCH_THRESHOLD = 0.75


def _normalize_title(title: str) -> str:
    return " ".join("".join(
        c.lower() if c.isalnum() or c.isspace() else " " for c in title
    ).split())


def _titles_match(query_title: str, candidate_title: str) -> bool:
    """Fuzzy title equality — guards against the resolver returning a
    lexically-nearby but different paper (the wrong-arXiv-paper bug).

    Note: SerpApi/Scholar titles are frequently truncated mid-phrase with an
    ellipsis. SequenceMatcher scores a truncated-prefix vs. full-title
    comparison via longest-matching-blocks, so a genuine truncation of the
    same title still clears the threshold; a different paper does not. If the
    query title itself is truncated, we compare on its available prefix.
    """
    a, b = _normalize_title(query_title), _normalize_title(candidate_title)
    if not a or not b:
        return False
    ratio = SequenceMatcher(None, a, b).ratio()
    # Truncation tolerance: if one title is a clean prefix of the other,
    # accept it regardless of length-driven ratio penalty.
    if ratio < _TITLE_MATCH_THRESHOLD:
        shorter, longer = sorted((a, b), key=len)
        if len(shorter) >= 12 and longer.startswith(shorter):
            logger.info(
                "Accepting resolver match on title-prefix (ratio %.2f) "
                "(%r vs %r)", ratio, query_title, candidate_title,
            )
            return True
        logger.info(
            "Rejecting resolver match — title similarity %.2f below %.2f "
            "(%r vs %r)", ratio, _TITLE_MATCH_THRESHOLD, query_title,
            candidate_title,
        )
        return False
    return True


def _is_known_open_host(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(p in netloc for p in KNOWN_OPEN_HOST_PATTERNS)


def _url_is_reachable(url: str) -> bool:
    """Cheap probe: does the URL respond without an auth/error status?
    Catches the 'OpenAlex says is_oa but the publisher URL 403s' case
    (SAGE ?download=true, bare doi.org links) before we ever hand the
    URL to extraction. Uses the shared scraping session so anti-bot
    behaviour matches the real fetch."""
    try:
        resp = _probe_session.head(url, timeout=5, allow_redirects=True)
        if resp.status_code == 405:  # some servers reject HEAD
            resp = _probe_session.get(
                url, timeout=5, stream=True, allow_redirects=True
            )
            resp.close()
        return 200 <= resp.status_code < 300
    except Exception as exc:
        logger.info("OA URL reachability probe failed for %s: %s", url, exc)
        return False


def _validate_oa_url(url: str) -> bool:
    """Known-open hosts are trusted outright; anything else (publisher
    domains, doi.org redirects) must pass the reachability probe."""
    if _is_known_open_host(url):
        return True
    return _url_is_reachable(url)


def resolve_oa_openalex(title: str) -> Optional[str]:
    """
    Query OpenAlex by title to find an Open Access URL.
    Returns the OA URL if found, title-verified, and validated, else None.
    """
    try:
        url = f"https://api.openalex.org/works?filter=title.search:{requests.utils.quote(title)}&per-page=1"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                best_match = data["results"][0]
                if not _titles_match(title, best_match.get("display_name", "")):
                    return None
                oa_info = best_match.get("open_access", {})
                if oa_info.get("is_oa") and oa_info.get("oa_url"):
                    oa_url = oa_info["oa_url"]
                    if _validate_oa_url(oa_url):
                        return oa_url
                    logger.info(
                        "OpenAlex OA URL failed validation, discarding: %s",
                        oa_url,
                    )
    except Exception as exc:
        logger.warning(f"OpenAlex resolution failed for {title!r}: {exc}")
    return None


def resolve_oa_semanticscholar(title: str) -> dict:
    """
    Query Semantic Scholar by title.
    Returns a dict with 'oa_url' (if an open access PDF is found) and 'tldr' (if available).
    """
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={requests.utils.quote(title)}&fields=title,openAccessPdf,tldr,authors,year&limit=1"
        headers = {}
        if settings.SEMANTIC_SCHOLAR_API_KEY:
            headers["x-api-key"] = settings.SEMANTIC_SCHOLAR_API_KEY

        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                best_match = data["data"][0]
                result = {}
                # Title check FIRST — a TLDR for the wrong paper is worse than
                # none, since it gets injected into the extraction prompt as
                # authoritative context.
                if not _titles_match(title, best_match.get("title", "")):
                    return {}
                if best_match.get("openAccessPdf") and best_match["openAccessPdf"].get("url"):
                    candidate = best_match["openAccessPdf"]["url"]
                    if _validate_oa_url(candidate):
                        result["oa_url"] = candidate
                    else:
                        logger.info(
                            "S2 OA URL failed validation, discarding: %s",
                            candidate,
                        )
                if best_match.get("tldr") and best_match["tldr"].get("text"):
                    result["tldr"] = best_match["tldr"]["text"]
                return result
    except Exception as exc:
        logger.warning(f"Semantic Scholar resolution failed for {title!r}: {exc}")
    return {}


def resolve_paper_oa(title: str) -> dict:
    """
    Orchestrates OA resolution using OpenAlex as primary and Semantic Scholar as secondary.
    Returns a dict: {"oa_url": str | None, "tldr": str | None}
    """
    result = {"oa_url": None, "tldr": None}

    # Primary: OpenAlex
    oa_url = resolve_oa_openalex(title)
    if oa_url:
        result["oa_url"] = oa_url
        logger.info(f"Resolved OA URL via OpenAlex: {oa_url}")

    # Secondary: Semantic Scholar
    if not result["oa_url"]:
        s2_res = resolve_oa_semanticscholar(title)
        if s2_res.get("oa_url"):
            result["oa_url"] = s2_res["oa_url"]
            logger.info(f"Resolved OA URL via Semantic Scholar: {s2_res['oa_url']}")
        if s2_res.get("tldr"):
            result["tldr"] = s2_res["tldr"]
            logger.info(f"Found TLDR via Semantic Scholar")

    return result
