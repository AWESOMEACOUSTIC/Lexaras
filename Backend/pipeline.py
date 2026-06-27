from agents import build_search_agent, build_reader_agent, writer_chain, critic_chain

def research_pipeline(topic: str) -> dict:
    
    state = {}

    #search agent work
    print("\n" + " =" *30)
    print(f"Starting research for topic : {topic}")
    print(" =" *30 + "\n")
    search_agent = build_search_agent(topic)
    search_result = search_agent.invoke({
        "messages": [("user", f"Find recent, reliable and detailed research information on the topic: {topic}")]
    })
    messages = search_result.get('messages', [])
    raw_content = messages[-1].content if messages else ""
    if isinstance(raw_content, list):
        state["search_results"] = " ".join(block.get("text", "") for block in raw_content if isinstance(block, dict))
    else:
        state["search_results"] = str(raw_content)
    print("\n search results: \n",state["search_results"])

    #reader agent work
    print("\n" + " =" *30)
    print("Reading The Web")
    print(" =" *30 + "\n")
    # Extract URLs from the search results text
    import re
    urls = re.findall(r'https?://[^\s\)\]\"\']+', state["search_results"])
    reader_agent = build_reader_agent(urls)
    reader_result = reader_agent.invoke({
        "messages": [("user", f"""
        Read the research information on '{topic}' 
        and provide a detailed summary by scraping the content from the urls
        Search Results: {state["search_results"][:800]}
        """)]
    })
    reader_messages = reader_result.get('messages', [])
    raw_reader = reader_messages[-1].content if reader_messages else ""
    if isinstance(raw_reader, list):
        state["reader_results"] = " ".join(block.get("text", "") for block in raw_reader if isinstance(block, dict))
    else:
        state["reader_results"] = str(raw_reader)
    print("\n reader results: \n",state["reader_results"])
    

    #writer agent work
    print("\n" + " =" *30)
    print("Writing The Report")
    print(" =" *30 + "\n")

    research_combined = (
        f"Search Results: {state['search_results']}\n\n"
        f"Detailed Scraped Content: {state['reader_results']}\n"
    )

    writer_result = writer_chain.invoke({
        "topic": topic,
        "research": research_combined,
        "content": state["reader_results"],
    })
    state["writer_results"] = writer_result
    print("\n writer results: \n",state["writer_results"])


    #Critic Report Work
    print("\n" + "=" * 30)
    print("Checking The Report...")
    print("=" * 30 + "\n")
    critic_result = critic_chain.invoke({
        "topic": topic,
        "report": state["writer_results"],
    })
    state["critic_results"] = critic_result
    print("\n critic results: \n",state["critic_results"])

    return state


if __name__ == "__main__":
    topic = input("\n Enter a research topic: ")
    results = research_pipeline(topic)
    
    print("\n" + "=" * 30)
    print("Final Research Report")
    print("=" * 30 + "\n")
    print(results["writer_results"])
    
    print("\n" + "=" * 30)
    print("Critic Feedback")
    print("=" * 30 + "\n")
    print(results["critic_results"])