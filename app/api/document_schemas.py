from typing import Optional

from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    chunks_indexed: int


class DocumentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None


class DocumentQueryResponse(BaseModel):
    answer: str
    sources: list[str]


class DocumentInfo(BaseModel):
    document_id: str
    filename: str