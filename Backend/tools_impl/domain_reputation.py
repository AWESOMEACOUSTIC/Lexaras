"""
A small, self-contained feedback loop: after every extraction attempt,
record whether that domain's page was actually usable. Over time this lets
discovery deprioritize domains that reliably fail extraction (paywalled
publishers, JS-heavy blog platforms) in favor of domains that reliably
succeed — turning a static, one-shot filtering decision into a system that
improves with usage, per the Bug 2 strategy doc's point 3.

Deliberately simple for this pass: an in-memory dict, best-effort persisted
to a local JSON file so it survives across pipeline runs within the same
deployment. A production system with concurrent workers would want a real
datastore (Redis, a small SQLite table) instead of a JSON file — noted here
as a known scope limitation rather than solved, since a file-based store is
enough to prove the feedback loop out.
"""

import json
import logging
import os
import threading
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_REPUTATION_FILE = os.environ.get(
    "LEXARAS_DOMAIN_REPUTATION_FILE",
    os.path.join(os.path.dirname(__file__), ".domain_reputation_cache.json"),
)

# A domain needs at least this many recorded attempts before its measured
# success rate is trusted over the neutral default — avoids one bad break-in
# permanently blacklisting a domain we've barely seen.
_MIN_SAMPLES_FOR_CONFIDENCE = 3

# New/unseen domains get this score that is neutral-to-slightly-optimistic,
# so they aren't penalised relative to established domains before any evidence exists.
_DEFAULT_REPUTATION = 0.6

# Chronic-offender hard filter: only trips once have enough samples AND
# the success rate is very low & reserved for domains that are essentially
# never extractable (e.g. a publisher that always paywalls).
HARD_BLOCK_MIN_SAMPLES  = 5
HARD_BLOCK_SUCCESS_RATE = 0.15

_lock = threading.Lock()
_stats: dict[str, dict[str, int]] = {}
_loaded = False


def _domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return "unknown"
    return netloc[4:] if netloc.startswith("www.") else netloc


def _load() -> None:
    global _stats, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if os.path.exists(_REPUTATION_FILE):
            with open(_REPUTATION_FILE, "r", encoding="utf-8") as f:
                _stats = json.load(f)
            logger.info("[DomainReputation] Loaded %d domain(s) from %s", len(_stats), _REPUTATION_FILE)
    except Exception as exc:
        logger.warning("[DomainReputation] Failed to load reputation cache, starting fresh: %s", exc)
        _stats = {}


def _save() -> None:
    try:
        with open(_REPUTATION_FILE, "w", encoding="utf-8") as f:
            json.dump(_stats, f, indent=2, sort_keys=True)
    except Exception as exc:
        # Never let a disk-write failure interrupt the pipeline — the
        # feedback loop degrades gracefully to "in-memory only for this run".
        logger.warning("[DomainReputation] Failed to persist reputation cache: %s", exc)


def record_outcome(url: str, success: bool) -> None:
    """
    Record whether an extraction attempt against this URL's domain succeeded.
    Call this once per extraction attempt, using the SCRAPE's success/failure
    (i.e. did we get usable page content), not the paper's ultimate fate in
    the report.
    """
    _load()
    domain = _domain_of(url)
    with _lock:
        entry = _stats.setdefault(domain, {"success": 0, "failure": 0})
        entry["success" if success else "failure"] += 1
        _save()
    logger.info(
        "[DomainReputation] Recorded | domain=%s | success=%s | totals=%s",
        domain, success, _stats.get(domain),
    )


def get_reputation(url: str) -> float:
    """
    Returns a 0-1 success-rate estimate for this URL's domain. Domains with
    fewer than _MIN_SAMPLES_FOR_CONFIDENCE recorded attempts fall back to the
    neutral default rather than an unstable small-sample ratio.
    """
    _load()
    domain = _domain_of(url)
    entry = _stats.get(domain)
    if not entry:
        return _DEFAULT_REPUTATION

    total = entry["success"] + entry["failure"]
    if total < _MIN_SAMPLES_FOR_CONFIDENCE:
        return _DEFAULT_REPUTATION

    return entry["success"] / total


def is_domain_blocked(url: str) -> bool:
    """
    Chronic-offender hard filter — True only once a domain has accumulated
    enough samples and its success rate is very low. Used as an optional,
    stronger filter beyond the soft re-ranking `get_reputation` enables.
    """
    _load()
    domain = _domain_of(url)
    entry = _stats.get(domain)
    if not entry:
        return False
    total = entry["success"] + entry["failure"]
    if total < HARD_BLOCK_MIN_SAMPLES:
        return False
    return (entry["success"] / total) < HARD_BLOCK_SUCCESS_RATE


def reset_for_testing() -> None:
    """Test-only helper — clears in-memory state and forces a reload next call."""
    global _stats, _loaded
    _stats = {}
    _loaded = False