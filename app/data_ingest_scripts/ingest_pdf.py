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
    print(f"[find_pdfs] Scanning '{data_dir}/' for PDF files...")
    files = glob.glob(os.path.join(data_dir, "*.pdf"))
    if not files:
        raise FileNotFoundError(f"No PDF files found in '{data_dir}/'")
    print(f"[find_pdfs] Found {len(files)} file(s): {files}")
    return files


def _build_chroma_client() -> chromadb.PersistentClient:
    chroma_path = Path(CHROMA_DIR or "./chroma_db")
    chroma_path.mkdir(parents=True, exist_ok=True)
    print(f"[chroma] Using directory: {chroma_path.resolve()}")
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
    print("=" * 60)
    print("ingest_pdf starting")
    print("=" * 60)

    print(f"[config] GOOGLE_EMBED_MODEL = {GOOGLE_EMBED_MODEL}")
    print(f"[config] GOOGLE_API_KEY     = {'set' if GOOGLE_API_KEY else 'NOT SET'}")
    print(f"[config] CHROMA_DIR         = {CHROMA_DIR}")

    pdf_files = _find_pdfs()

    print(f"\n[embed] Initialising GoogleGenerativeAIEmbeddings with model '{GOOGLE_EMBED_MODEL}'...")
    try:
        embed = GoogleGenerativeAIEmbeddings(
            model=GOOGLE_EMBED_MODEL,
            google_api_key=GOOGLE_API_KEY,
        )
        print("[embed] Embedding model initialised OK")
    except Exception as e:
        print(f"[embed] ERROR initialising embedding model: {e}")
        raise

    print("\n[chroma] Connecting to ChromaDB...")
    try:
        client     = _build_chroma_client()
        collection = client.get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"[chroma] Collection '{_COLLECTION}' ready. Current item count: {collection.count()}")
    except Exception as e:
        print(f"[chroma] ERROR connecting to ChromaDB: {e}")
        raise

    print("\n[docling] Initialising DocumentConverter (downloads models on first run)...")
    try:
        converter = DocumentConverter()
        chunker   = HybridChunker()
        print("[docling] Converter and chunker ready")
    except Exception as e:
        print(f"[docling] ERROR initialising Docling: {e}")
        raise

    total_chunks = 0

    for pdf_path in pdf_files:
        filename = Path(pdf_path).name
        print(f"\n{'─' * 50}")
        print(f"[parse] Processing: {filename}")

        print(f"[parse] Running Docling converter on {filename}...")
        try:
            result = converter.convert(pdf_path)
            print(f"[parse] Conversion done for {filename}")
        except Exception as e:
            print(f"[parse] ERROR converting {filename}: {e}")
            continue

        print(f"[chunk] Chunking document...")
        try:
            chunks = list(chunker.chunk(result.document))
            print(f"[chunk] {len(chunks)} raw chunk(s) produced")
        except Exception as e:
            print(f"[chunk] ERROR chunking {filename}: {e}")
            continue

        if not chunks:
            print(f"[chunk] WARNING: No chunks produced from {filename} — skipping.")
            continue

        ids, documents, embeddings, metadatas = [], [], [], []

        for i, chunk in enumerate(chunks):
            text = chunk.text.strip()
            if not text:
                print(f"[chunk]   chunk {i} is empty — skipping")
                continue

            chunk_id = f"{filename}::c{i}"
            meta = {"source": filename, "chunk": i}
            meta.update(_chunk_metadata(chunk))
            print(f"[chunk]   chunk {i}: {len(text)} chars | meta: {meta}")

            print(f"[embed]   embedding chunk {i}...")
            try:
                vector = embed.embed_query(text)
                print(f"[embed]   chunk {i} embedded OK (dim={len(vector)})")
            except Exception as e:
                print(f"[embed]   ERROR embedding chunk {i}: {e} — skipping chunk")
                continue

            ids.append(chunk_id)
            documents.append(text)
            embeddings.append(vector)
            metadatas.append(meta)

        if not documents:
            print(f"[chunk] WARNING: All chunks were empty or failed to embed in {filename} — skipping.")
            continue

        print(f"\n[chroma] Upserting {len(documents)} chunk(s) into collection '{_COLLECTION}'...")
        try:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            print(f"[chroma] Upsert successful for {filename}")
        except Exception as e:
            print(f"[chroma] ERROR upserting {filename}: {e}")
            continue

        total_chunks += len(documents)

    print(f"\n{'=' * 60}")
    print(f"Ingest complete.")
    print(f"  Total chunks upserted : {total_chunks}")
    print(f"  Collection item count  : {collection.count()}")
    print("=" * 60)
