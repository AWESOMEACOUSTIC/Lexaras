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

# `creative_llm` is kept for any task that genuinely wants expressive,
# lower-probability word choices (e.g. brainstorming, casual copy).
creative_llm = _make_llm(temperature=0.5)

# `academic_llm` is dedicated to tasks that must hold a rigorous, consistent
# academic register — currently the writer node and its self-critique/revise
# pass. Low temperature favours the most standard, expected phrasing over
# expressive variation, which is what a research report needs and what
# `creative_llm`'s higher temperature was actively working against.
academic_llm = _make_llm(temperature=0.15)