from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")

DB_URL = os.getenv("DB_URL")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY")
GOOGLE_EMBED_MODEL = os.getenv("GOOGLE_EMBED_MODEL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL")