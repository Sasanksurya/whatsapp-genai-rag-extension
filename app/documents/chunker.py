"""
Chunking: splits extracted document text into overlapping chunks
sized for embedding + retrieval.

Deliberately simple (character-based with paragraph-aware breaks)
rather than pulling in a heavier text-splitter library — this is
easy to reason about and swap out later if retrieval quality needs
a smarter splitter (e.g. sentence-aware or token-aware).
"""
from app.core.config import settings


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    chunk_size = chunk_size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap

    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 1 <= chunk_size:
            current = f"{current}\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # start new chunk, carrying overlap from the end of the previous one
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail}\n{para}" if tail else para

    if current:
        chunks.append(current)

    # Fallback: a single paragraph longer than chunk_size on its own
    final: list[str] = []
    for c in chunks:
        if len(c) <= chunk_size * 1.5:
            final.append(c)
        else:
            for i in range(0, len(c), chunk_size - overlap):
                final.append(c[i:i + chunk_size])

    return final
