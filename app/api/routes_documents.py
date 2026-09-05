from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.document_schemas import (
    DocumentInfo,
    DocumentQueryRequest,
    DocumentQueryResponse,
    IngestResponse,
)
from app.core.audit import log_event
from app.core.auth import get_current_owner
from app.documents.extractors import UnsupportedFileType
from app.rag.pipeline import answer_query, ingest_document
from app.rag.vectorstore import vector_store

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_UPLOAD_BYTES = 10_000_000  # 10MB cap


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    owner_id: str = Depends(get_current_owner),
):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_BYTES} byte limit.")

    try:
        result = ingest_document(filename=file.filename, data=data, owner_id=owner_id)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    log_event(owner_id, "document_upload", {"filename": file.filename, "chunks": result["chunks_indexed"]})
    return IngestResponse(**result)


@router.post("/query", response_model=DocumentQueryResponse)
def query_documents(payload: DocumentQueryRequest, owner_id: str = Depends(get_current_owner)):
    try:
        result = answer_query(query=payload.query, owner_id=owner_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM provider error: {e}")

    log_event(owner_id, "document_query", {"query": payload.query, "sources": result["sources"]})
    return DocumentQueryResponse(**result)


@router.get("", response_model=list[DocumentInfo])
def list_documents(owner_id: str = Depends(get_current_owner)):
    docs = vector_store.list_documents(owner_id=owner_id)
    return [DocumentInfo(**d) for d in docs]
