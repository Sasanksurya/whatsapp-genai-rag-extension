"""
MCP Agent.

Fetches authorized external content (website or Google Drive file)
and ingests it through the exact same chunk -> embed -> store
pipeline as uploaded documents (Phase 2), so `/converse` and
`/documents/query` retrieval automatically includes it — no
duplicate retrieval logic needed.
"""
from app.documents.chunker import chunk_text
from app.mcp.drive_client import fetch_drive_file_text
from app.mcp.website_fetcher import fetch_url_text
from app.rag.vectorstore import new_document_id, vector_store


def ingest_website(url: str, owner_id: str) -> dict:
    text = fetch_url_text(url)
    chunks = chunk_text(text)
    document_id = new_document_id()
    count = vector_store.add_document_chunks(
        chunks=chunks,
        owner_id=owner_id,
        document_id=document_id,
        filename=url,
        source_type="web",
    )
    return {"document_id": document_id, "filename": url, "chunks_indexed": count}


def ingest_drive_file(owner_id: str, file_id: str) -> dict:
    text, filename = fetch_drive_file_text(owner_id, file_id)
    chunks = chunk_text(text)
    document_id = new_document_id()
    count = vector_store.add_document_chunks(
        chunks=chunks,
        owner_id=owner_id,
        document_id=document_id,
        filename=filename,
        source_type="drive",
    )
    return {"document_id": document_id, "filename": filename, "chunks_indexed": count}
