from pydantic import BaseModel

from app.api.converse_schemas import ConverseResponse


class TranscribeResponse(BaseModel):
    transcript: str


class ConverseVoiceResponse(ConverseResponse):
    transcript: str
