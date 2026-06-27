""" 
What is the difference between using old create_react agent and the modern new way.
What has been changed and how this modern approach is better than the old one? 
"""


from langgraph.prebuilt import create_react_agent
from tools import web_search, scrape_url
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import os
from dotenv import load_dotenv
from rich import print


load_dotenv()


mistral = ChatMistralAI(
    model="mistral-small-2603",
    api_key=os.getenv("MISTRAL_API_KEY")
)

def build_search_agent(query : str):
    return create_react_agent(
        model=mistral,
        tools=[web_search],
        prompt=f"""
        You are a helpful assistant specialized in answering user queries. 
        Your current research topic is: {query}.
        You have access to a web search tool that can be used to find information on the internet.
        """,
    )


def build_reader_agent(urls : list[str]):
    return create_react_agent(
        model=mistral,
        tools=[scrape_url],
        prompt=f"""
        You are a helpful assistant specialized in summarizing web content.
        You have access to a scraper tool.
        You may need to scrape the following URLs:
        {chr(10).join(urls)}
        """,
    )

#writer chain
writer_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are an expert research writer who is specialized in writing content making in clean, clear structured and well-structured manner reports.
You always use the headings, bold text, and explainable bullet points to make the report more readable.
"""),
    ("human", """Here is the content you need to write a report on:
    Topic: {topic}
    Research Gathered: {research}
    Content: {content}

    Structure the report as:
    - Introduction
    - Research Gathered:
    - Key Findings (minimum 5 points in detailed explainable points)
    - Conclusion
    - Sources (List all URLS found in the research)

    Be detailed, factual and comprehensive, avoid fluff.
"""),
])

output_parser = StrOutputParser()
writer_chain = writer_prompt | mistral | output_parser


#Critic Chain
critic_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    You are an expert critic and fact-checker for research reports. Your job is to review the report written by the writer and check for accuracy, completeness, clarity, and overall quality. You should be thorough and honest in your assessment.
    """),
    ("human", """Here is the research report you need to review:
    Topic: {topic}
    Writer's Report: {report}
    
    Please provide your feedback on the following: 
    - Accuracy: Are the facts correct? (Fact check if needed)
    - Completeness: Is the topic fully covered?
    - Clarity: Is the report easy to understand?
    - Structure: Is the report well-organized?
    
    If you find any issues, please point them out and suggest improvements. If the report is excellent, please acknowledge it.
    """),
])

critic_chain = critic_prompt | mistral | output_parser