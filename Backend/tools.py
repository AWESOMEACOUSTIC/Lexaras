from requests import request
from langchain_core.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv
from rich import print


load_dotenv()

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

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

# print(web_search.invoke({"query": "what are the recent news on war?"}))

@tool
def scrape_url(url : str) -> str:
    """
    Scrape the content of a given URL and return clean text content from a given URL for deeper reading.
    """
    try:
        header = requests.get(url, timeout = 8, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'})
        header.raise_for_status()
        soup = BeautifulSoup(header.text, 'html.parser')
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside']): # Removing useless tags.
            tag.decompose()
        text = soup.get_text(separator='\n', strip=True)
        return text[:2000]
    except Exception as e:
        return f"Error scraping URL: {str(e)}"

print(scrape_url.invoke({"url": "https://www.bbc.com/sport/football/articles/cd95zlv7jz7o"}))