"""
Voice Agent — speech-to-text.

Uses faster-whisper (open-source Whisper, runs locally) instead of a
paid STT API, consistent with the project's zero-cost decision.
The model downloads once on first use and then runs fully offline.
"""
import os
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

from app.core.config import settings

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            settings.whisper_model_size,
            device="cpu",
            compute_type="int8",
        )
    return _model


def transcribe_audio(
    data: bytes,
    filename_hint: str = "audio.wav",
) -> str:
    """
    Convert audio bytes to text using faster-whisper.

    On Windows, the temporary file must be closed before
    faster-whisper/PyAV opens it. Therefore, we create the
    temporary file with delete=False, close it, transcribe it,
    and finally remove it.
    """
    suffix = Path(filename_hint).suffix or ".wav"
    # Create and close the temporary file first.
    with tempfile.NamedTemporaryFile(
        suffix=suffix,
        delete=False,
    ) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        # The temporary file is now closed.
        # PyAV can safely open it on Windows.
        model = get_model()
        segments, _info = model.transcribe(
            tmp_path,
            beam_size=5,
        )
        text = " ".join(
            segment.text.strip()
            for segment in segments
        )
        return text.strip()
    finally:
        # Always delete the temporary file.
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
