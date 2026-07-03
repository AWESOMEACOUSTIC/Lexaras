"""
tools.py — Lexaras Research Platform
-------------------------------------
Exposes all LangChain-compatible tools from the refactored tools package.
"""

from tools_impl.web_search import web_search
from tools_impl.scrape_url import scrape_url
from tools_impl.extract_pdf import extract_pdf

ALL_TOOLS = [web_search, scrape_url, extract_pdf]
DISCOVERY_TOOLS = [web_search]
READER_TOOLS = [scrape_url, extract_pdf]