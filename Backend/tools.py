from langchain_core.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv
from rich import print


load_dotenv()

tavily = TavilyClient(api_key=os.getenv("tavily_api_key"))

@tool
def web_search(query : str) -> str:
    """
    Perform web search using Tavily search engine and return the reliable information on a topic. Returns Titles, URLs and snippets.
    """
    try:
        search_result = tavily.search(query=query, max_results=2, include_content=True)
        out = []
        for i, r in enumerate(search_result["results"]):
            out.append(f"""
            Result {i+1}:
            Title: {r['title']}
            URL: {r['url']}
            Snippet: {r['content'][:300]}
            """)
        content = "\n-----\n".join(out)
        return content
    except Exception as e:
        return f"Error searching the web: {str(e)}"

print(web_search.invoke({"query": "what are the recent news on war?"}))