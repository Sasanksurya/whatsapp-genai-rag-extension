from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    document_id: str
    filename: str
    chunks_indexed: int


class DocumentQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class DocumentQueryResponse(BaseModel):
    answer: str
    sources: list[str]


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
