from pydantic import BaseModel, Field


class ConverseRequest(BaseModel):
    conversation_id: str = Field(..., description="Groups turns into one chat thread")
    message: str = Field(..., min_length=1, max_length=4000)


class ConverseResponse(BaseModel):
    reply: str
    agent_used: str
    resolved_query: str
    sources: list[str]
    verified: bool | None
