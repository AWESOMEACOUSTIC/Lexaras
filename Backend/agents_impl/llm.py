from langchain_mistralai import ChatMistralAI
from config import settings

def _make_llm(temperature: float = 0.2) -> ChatMistralAI:
    return ChatMistralAI(
        model="mistral-small-2603",
        api_key=settings.MISTRAL_API_KEY,
        temperature=temperature,
        max_retries=3,
        timeout=60,
    )

llm = _make_llm(temperature=0.2)        
creative_llm = _make_llm(temperature=0.5) 
