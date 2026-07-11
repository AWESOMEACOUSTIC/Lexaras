import logging
import requests
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

def resolve_oa_openalex(title: str) -> Optional[str]:
    """
    Query OpenAlex by title to find an Open Access URL.
    Returns the OA URL if found, else None.
    """
    try:
        url = f"https://api.openalex.org/works?filter=title.search:{requests.utils.quote(title)}&per-page=1"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                best_match = data["results"][0]
                oa_info = best_match.get("open_access", {})
                if oa_info.get("is_oa") and oa_info.get("oa_url"):
                    return oa_info["oa_url"]
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
                if best_match.get("openAccessPdf") and best_match["openAccessPdf"].get("url"):
                    result["oa_url"] = best_match["openAccessPdf"]["url"]
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
