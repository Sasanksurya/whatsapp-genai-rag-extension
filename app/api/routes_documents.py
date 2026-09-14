from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.document_schemas import (
    DocumentInfo,
    DocumentQueryRequest,
    DocumentQueryResponse,
    IngestResponse,
)
from app.core.audit import log_event
from app.core.auth import get_current_owner
from app.core.conversation_verification import verify_conversation_membership
from app.documents.extractors import UnsupportedFileType
from app.rag.pipeline import answer_query, ingest_document
from app.rag.vectorstore import vector_store


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


MAX_UPLOAD_BYTES = 10_000_000  # 10MB cap


@router.post("/upload", response_model=IngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    owner_id: str = Depends(get_current_owner),
):
    """
    Upload and index a document for a conversation.

    Security:
    - owner_id comes from the authenticated API key.
    - conversation_id comes from the request as the resource being accessed.
    - Node backend verifies that owner_id is a member of conversation_id.
    - The conversation_id is stored with every vector chunk.
    """

    if not conversation_id:
        raise HTTPException(
            status_code=400,
            detail="conversation_id is required for document uploads.",
        )

    # Verify that the authenticated user is actually a member
    # of the requested conversation.
    verify_conversation_membership(
        conversation_id,
        owner_id,
    )

    data = await file.read()

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_BYTES} byte limit.",
        )

    try:
        result = ingest_document(
            filename=file.filename,
            data=data,
            owner_id=owner_id,
            conversation_id=conversation_id,
        )

    except UnsupportedFileType as e:
        raise HTTPException(
            status_code=415,
            detail=str(e),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )

    log_event(
        owner_id,
        "document_upload",
        {
            "filename": file.filename,
            "conversation_id": conversation_id,
            "chunks": result["chunks_indexed"],
        },
    )

    return IngestResponse(**result)


@router.post(
    "/query",
    response_model=DocumentQueryResponse,
)
def query_documents(
    payload: DocumentQueryRequest,
    owner_id: str = Depends(get_current_owner),
):
    """
    Query documents belonging only to the authenticated user
    and the requested conversation.

    Security has two layers:

    1. Node verifies conversation membership.
    2. ChromaDB filters retrieval using both owner_id
       and conversation_id.
    """

    if not payload.conversation_id:
        raise HTTPException(
            status_code=400,
            detail="conversation_id is required for document queries.",
        )

    # First authorization boundary:
    # confirm the authenticated user belongs to the conversation.
    verify_conversation_membership(
        payload.conversation_id,
        owner_id,
    )

    try:
        result = answer_query(
            query=payload.query,
            owner_id=owner_id,
            conversation_id=payload.conversation_id,
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {e}",
        )

    log_event(
        owner_id,
        "document_query",
        {
            "query": payload.query,
            "conversation_id": payload.conversation_id,
            "sources": result["sources"],
        },
    )

    return DocumentQueryResponse(**result)


@router.get(
    "",
    response_model=list[DocumentInfo],
)
def list_documents(
    conversation_id: Optional[str] = None,
    owner_id: str = Depends(get_current_owner),
):
    """
    List documents belonging to the authenticated user.

    If conversation_id is provided, only documents from that
    conversation are returned.
    """

    if conversation_id:
        # Verify membership before exposing conversation documents.
        verify_conversation_membership(
            conversation_id,
            owner_id,
        )

    docs = vector_store.list_documents(
        owner_id=owner_id,
        conversation_id=conversation_id,
    )

    return [
        DocumentInfo(**d)
        for d in docs
    ]