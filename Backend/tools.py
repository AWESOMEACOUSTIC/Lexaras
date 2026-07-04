"""
tools.py — Lexaras Research Platform
-------------------------------------
All LangChain-compatible tools used by the agent pipeline.

Tools:
    web_search          — Tavily web search (general web, blogs, preprints)
    scholar_search      — Google Scholar search via SerpApi with year-descending
                          windowed strategy; returns structured academic metadata
    scrape_url          — Robust HTML scraper with retry and sentence-boundary trim
    extract_pdf         — pdfplumber-based PDF text extractor
"""

from tools_impl.web_search import web_search
from tools_impl.scholar_search import scholar_search
from tools_impl.scrape_url import scrape_url
from tools_impl.extract_pdf import extract_pdf

ALL_TOOLS      = [web_search, scholar_search, scrape_url, extract_pdf]
SCHOLAR_TOOLS  = [scholar_search]          # used by discovery in scholar_only mode
WEB_TOOLS      = [web_search]              # used by discovery for web fill in default mode
DISCOVERY_TOOLS = [web_search, scholar_search]   # full set for default mode
READER_TOOLS   = [scrape_url, extract_pdf]