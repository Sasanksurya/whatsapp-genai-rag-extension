"""
Centralized application settings.

Loads from environment variables / .env file. This is the ONLY place
that should read os.environ for config — every other module imports
`settings` from here.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider (Groq — free tier, no Anthropic key used)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    app_env: str = "development"
    log_level: str = "INFO"

    # RAG (Phase 2) — local, free embeddings + local vector store
    embedding_model_name: str = "all-MiniLM-L6-v2"
    chroma_persist_dir: str = "./data/chroma"
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 8
    # Cosine distance (0=identical, 2=opposite) below which a retrieved
    # chunk is considered relevant enough to override the intent
    # classifier — see orchestrator.py. Conservative default; tune based
    # on real testing with your embedding model, since this couldn't be
    # verified against live embeddings in the sandboxed build environment.
    relevance_distance_threshold: float = 0.9

    # WhatsApp Business Platform (Phase 6)
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    # MCP (Phase 4) — Google Drive OAuth
    google_client_secrets_file: str = "credentials.json"
    google_oauth_redirect_uri: str = "http://127.0.0.1:8000/api/v1/mcp/drive/callback"

    # Voice (Phase 4) — local Whisper, no API key needed
    whisper_model_size: str = "base"

    # Security (Phase 5)
    rate_limit_max_requests: int = 30
    rate_limit_window_seconds: int = 60
    drive_token_encryption_key: str = ""


settings = Settings()
