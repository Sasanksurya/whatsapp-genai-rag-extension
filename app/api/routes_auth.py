from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.auth import create_api_key

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, max_length=128)


class RegisterResponse(BaseModel):
    api_key: str
    note: str = "Save this now — it will not be shown again. Send it as the X-API-Key header on every request."


@router.post("/register", response_model=RegisterResponse)
def register(payload: RegisterRequest):
    key = create_api_key(payload.owner_id)
    return RegisterResponse(api_key=key)
