# ============================================================
# backend/ai_engine/ingestion.py
# The INGESTION pipeline: PDF -> text -> chunks -> vectors -> Qdrant.
#
# This runs when an admin uploads a PDF. It makes the document
# searchable so Phase 5's retrieval can later find relevant chunks.
#
# Pipeline (each step is a function you can test in isolation):
#   1. extract_text            PyMuPDF: PDF bytes -> page texts
#   2. chunk_text              recursive splitting w/ overlap
#   3. store_chunks            embed each chunk + upsert into Qdrant
#
# CHUNKING STRATEGY (why recursive + overlap):
#   - Recursive: split along natural boundaries (paragraph->sentence->word)
#     so we never cut mid-sentence when we can avoid it.
#   - Overlap: consecutive chunks share a few characters so a fact that
#     straddles a boundary still appears fully in at least one chunk.
# ============================================================

import uuid

import fitz  # PyMuPDF
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from ai_engine.embeddings import embed_batch
from config import settings
from security.pii_redactor import redact_pii

# Tuning knobs for chunking. These are deliberately named constants so we
# can reason about and experiment with them (Phase 9 eval will tune these).
CHUNK_SIZE = 500        # target chars per chunk
CHUNK_OVERLAP = 50      # chars shared with the previous chunk


# --- Step 1: Extract -----------------------------------------------------

def extract_text(pdf_bytes: bytes) -> list[str]:
    """Extract per-page text from a PDF. Returns a list: page_text[i] = page i."""
    pages: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pages.append(page.get_text())
    return pages


# --- Step 2: Chunk -------------------------------------------------------

def chunk_text(page_text: str, page_num: int, source: str) -> list[dict]:
    """Split a single page's text into overlapping chunks.

    Each returned dict: {text, page, chunk_index}. `chunk_index` is local
    to this page; the full doc index is assembled by the caller.

    Recursive splitting: try to cut at paragraph breaks, else near the
    chunk size, else hard-cut. This balances clean boundaries vs.
    guaranteed max length.
    """
    # Normalize whitespace so chunk sizes are predictable.
    text = " ".join(page_text.split())
    if not text.strip():
        return []

    chunks: list[dict] = []
    start = 0
    n = len(text)
    idx = 0

    while start < n:
        end = min(start + CHUNK_SIZE, n)

        # Prefer cutting at a paragraph/sentence boundary before the limit.
        if end < n:
            # Last paragraph break within the chunk:
            cut = text.rfind("\n\n", start, end)
            if cut == -1:
                cut = text.rfind(". ", start, end)
            if cut != -1 and cut > start:
                end = cut + 1  # include the period

        chunk_text_ = text[start:end]
        chunks.append(
            {"text": chunk_text_, "page": page_num, "chunk_index": idx}
        )
        idx += 1

        # Advance for the next chunk.
        if end < n:
            # Not at the end yet: overlap by CHUNK_OVERLAP chars so a fact
            # straddling a boundary still appears fully in the next chunk.
            # `start + 1` is a safety net guaranteeing progress (no infinite loop).
            start = max(end - CHUNK_OVERLAP, start + 1)
        else:
            # Reached the end of the text. There is no "next chunk" worth
            # emitting (any further chunk would be a tiny overlapping tail
            # fragment). Terminate the loop.
            start = n

    return chunks


# --- Step 3: Store -------------------------------------------------------

def get_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def ensure_collection(client: QdrantClient) -> None:
    """Create the Qdrant collection if it doesn't exist.

    We configure it for our embedding model: 768-dim vectors, COSINE
    distance (semantic similarity = direction, not magnitude).
    If it already exists (e.g. from a prior run), we leave it as-is.
    """
    collections = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        # Keyword index on rbac_label so phase-5 RBAC filtering is fast.
        # Without an index Qdrant scans every payload (slow on big collections);
        # with a KEYWORD index it can filter in O(log n).
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="rbac_label",
            field_schema=PayloadSchemaType.KEYWORD,
        )


async def ingest_pdf(
    pdf_bytes: bytes,
    source: str,
    rbac_label: str,
    ingested_by: str,
) -> dict:
    """Full pipeline: extract, chunk, embed, store. Returns a summary."""
    client = get_client()
    ensure_collection(client)

    # 1. Extract per-page text.
    pages = extract_text(pdf_bytes)

    # 2. Chunk each page, tagging page + doc-level metadata.
    doc_id = str(uuid.uuid4())
    chunks: list[dict] = []
    for page_num, page_text in enumerate(pages, start=1):
        page_chunks = chunk_text(page_text, page_num, source)
        for c in page_chunks:
            c["doc_id"] = doc_id
            c["source"] = source
            c["rbac_label"] = rbac_label
            c["ingested_by"] = ingested_by
        chunks.extend(page_chunks)

    if not chunks:
        return {"ingested": 0, "doc_id": doc_id, "error": "no readable text"}

    # 3. Redact PII from every chunk BEFORE embedding/storing, so PII never
    #    enters the vector DB or any downstream prompt.
    for c in chunks:
        c["text"] = redact_pii(c["text"])

    # 4. Embed all (redacted) chunk texts.
    texts = [c["text"] for c in chunks]
    vectors = await embed_batch(texts)

    # 5. Build Qdrant points: payload = metadata, vector = embedding.
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"text": c["text"], **{k: v for k, v in c.items() if k != "text"}},
        )
        for c, vector in zip(chunks, vectors)
    ]

    # 5. Upsert in one batch (atomic, efficient).
    client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
        wait=True,  # wait for index before returning so we know it's stored
    )

    return {"ingested": len(chunks), "doc_id": doc_id, "source": source}
