from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's message text")


class ChatResponse(BaseModel):
    reply: str
    model: str
