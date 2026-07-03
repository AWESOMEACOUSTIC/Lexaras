import os
from dotenv import load_dotenv

# Load environmental variables from .env file
load_dotenv()

class Settings:
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

settings = Settings()
