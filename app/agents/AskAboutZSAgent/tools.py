import chromadb
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import CHROMA_DIR, GOOGLE_API_KEY, GOOGLE_EMBED_MODEL
from app.logger import get_logger

logger = get_logger(__name__)

_embed = GoogleGenerativeAIEmbeddings(
    model=GOOGLE_EMBED_MODEL,
    google_api_key=GOOGLE_API_KEY,
)

_client = chromadb.PersistentClient(path=CHROMA_DIR or "./chroma_db")


def embed_query(text: str) -> list[float]:
    return _embed.embed_query(text)


def retrieve(question: str, n: int = 7) -> list[str]:
    collection = _client.get_or_create_collection("documents")
    query_embedding = embed_query(question)
    results = collection.query(query_embeddings=[query_embedding], n_results=n)
    chunks = results["documents"][0]
    logger.debug("Retrieved %d chunk(s) for query: %s", len(chunks), question)
    return chunks
