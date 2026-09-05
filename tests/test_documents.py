import pytest

from app.documents.chunker import chunk_text
from app.documents.extractors import UnsupportedFileType, extract_text, extract_txt


def test_extract_txt_decodes_utf8():
    assert extract_txt(b"hello world") == "hello world"


def test_extract_text_rejects_unsupported_extension():
    with pytest.raises(UnsupportedFileType):
        extract_text("malware.exe", b"data")


def test_extract_text_rejects_empty_content():
    with pytest.raises(ValueError):
        extract_text("empty.txt", b"   \n  ")


def test_chunk_text_respects_size_limit():
    long_text = "\n".join(f"line {i} with some content here" for i in range(200))
    chunks = chunk_text(long_text, chunk_size=300, overlap=50)
    assert all(len(c) <= 450 for c in chunks)  # allows the 1.5x fallback margin
    assert len(chunks) > 1


def test_chunk_text_handles_short_input():
    chunks = chunk_text("just one short line", chunk_size=800, overlap=120)
    assert chunks == ["just one short line"]
