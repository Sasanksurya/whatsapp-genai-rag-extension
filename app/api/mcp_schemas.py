from pydantic import BaseModel, Field


class IngestUrlRequest(BaseModel):
    url: str = Field(..., description="Must be a public http/https URL")


class IngestResult(BaseModel):
    document_id: str
    filename: str
    chunks_indexed: int


class DriveAuthUrlResponse(BaseModel):
    auth_url: str


class DriveIngestRequest(BaseModel):
    file_id: str = Field(..., description="Google Drive file ID")
