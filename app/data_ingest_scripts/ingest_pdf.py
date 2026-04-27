"""
Reads all PDF files found in data/, parses them with Docling (preserving
document structure, tables, and headings), chunks using Docling's HybridChunker,
generates embeddings with Google Generative AI, and upserts into a persistent
ChromaDB collection named 'documents'.

Run via: uv run ingest_pdf

Note: Docling downloads its ML models (~1 GB) on the first run.
"""
import glob
import os
from pathlib import Path

import chromadb
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config import CHROMA_DIR, GOOGLE_API_KEY, GOOGLE_EMBED_MODEL
from app.logger import get_logger

logger = get_logger(__name__)

_COLLECTION = "documents"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_pdfs(data_dir: str = "data") -> list[str]:
    files = glob.glob(os.path.join(data_dir, "*.pdf"))
    if not files:
        raise FileNotFoundError(f"No PDF files found in '{data_dir}/'")
    logger.info("Found %d PDF file(s)", len(files))
    return files


def _build_chroma_client() -> chromadb.PersistentClient:
    chroma_path = Path(CHROMA_DIR or "./chroma_db")
    chroma_path.mkdir(parents=True, exist_ok=True)
    logger.info("ChromaDB directory: %s", chroma_path.resolve())
    return chromadb.PersistentClient(path=str(chroma_path))


def _chunk_metadata(chunk) -> dict:
    """Extract the best available metadata from a Docling chunk."""
    meta: dict = {}
    try:
        page_no = chunk.meta.doc_items[0].prov[0].page_no
        if page_no is not None:
            meta["page"] = page_no
    except (AttributeError, IndexError):
        pass
    try:
        headings = chunk.meta.headings
        if headings:
            meta["headings"] = " > ".join(headings)
    except AttributeError:
        pass
    return meta

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    pdf_files = _find_pdfs()

    logger.info("Initialising embedding model '%s'...", GOOGLE_EMBED_MODEL)
    embed = GoogleGenerativeAIEmbeddings(
        model=GOOGLE_EMBED_MODEL,
        google_api_key=GOOGLE_API_KEY,
    )

    client     = _build_chroma_client()
    collection = client.get_or_create_collection(
        name=_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info("Initialising Docling converter (downloads models on first run)...")
    converter = DocumentConverter()
    chunker   = HybridChunker()

    total_chunks = 0

    for pdf_path in pdf_files:
        filename = Path(pdf_path).name
        logger.info("Parsing: %s", filename)

        result = converter.convert(pdf_path)
        chunks = list(chunker.chunk(result.document))

        if not chunks:
            logger.warning("No chunks produced from %s — skipping.", filename)
            continue
        logger.info("  %d chunk(s) extracted", len(chunks))

        ids, documents, metadatas = [], [], []

        for i, chunk in enumerate(chunks):
            text = chunk.text.strip()
            if not text:
                continue
            ids.append(f"{filename}::c{i}")
            documents.append(text)
            meta = {"source": filename, "chunk": i}
            meta.update(_chunk_metadata(chunk))
            metadatas.append(meta)

        if not documents:
            logger.warning("All chunks were empty in %s — skipping.", filename)
            continue

        logger.info("  Generating embeddings for %d chunk(s)...", len(documents))
        embeddings = embed.embed_documents(documents)

        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("  Upserted %d chunk(s) from %s", len(documents), filename)
        total_chunks += len(documents)

    logger.info("Ingest complete. Total chunks upserted: %d", total_chunks)
    logger.info("Collection '%s' now contains %d item(s).", _COLLECTION, collection.count())
