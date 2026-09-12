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

    # RAG — local, free embeddings + local vector store
    embedding_model_name: str = "all-MiniLM-L6-v2"
    chroma_persist_dir: str = "./data/chroma"
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 8
    relevance_distance_threshold: float = 0.9

    # MCP — Google Drive OAuth
    google_client_secrets_file: str = "credentials.json"
    google_oauth_redirect_uri: str = "http://127.0.0.1:8000/api/v1/mcp/drive/callback"

    # Voice — local Whisper, no API key needed
    whisper_model_size: str = "base"

    # Security
    rate_limit_max_requests: int = 30
    rate_limit_window_seconds: int = 60
    drive_token_encryption_key: str = ""

    # WhatsApp Business Platform (Meta)
    whatsapp_verify_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    # Twilio WhatsApp Sandbox
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""
    twilio_webhook_url: str = ""
    twilio_content_sid: str = ""


settings = Settings()