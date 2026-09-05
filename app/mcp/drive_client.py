"""
Google Drive integration for the MCP Agent (project spec section 8).

Requires the user to set up their OWN free Google Cloud project and
OAuth client credentials — see README "Google Drive setup" section.
This module never accesses a file the owner hasn't explicitly
authorized: it only acts using a token obtained through the real
Google OAuth consent screen for that specific owner_id.
"""
import io

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.documents.extractors import extract_text
from app.mcp.token_store import load_token, save_token

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google Workspace files (Docs/Sheets) need to be *exported* to a
# normal format before our existing extractors can read them.
EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
}


class DriveNotAuthorizedError(Exception):
    pass


def _flow(redirect_uri: str) -> Flow:
    return Flow.from_client_secrets_file(
        settings.google_client_secrets_file,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def build_auth_url(redirect_uri: str, state: str) -> str:
    flow = _flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


def exchange_code(owner_id: str, code: str, redirect_uri: str) -> None:
    flow = _flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    save_token(
        owner_id,
        {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes,
        },
    )


def _get_credentials(owner_id: str) -> Credentials:
    token_data = load_token(owner_id)
    if token_data is None:
        raise DriveNotAuthorizedError(
            f"Owner '{owner_id}' has not authorized Google Drive access yet. "
            "Call /mcp/drive/auth-url first and complete the consent flow."
        )
    creds = Credentials(**token_data)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        save_token(
            owner_id,
            {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": creds.scopes,
            },
        )
    return creds


def fetch_drive_file_text(owner_id: str, file_id: str) -> tuple[str, str]:
    """Returns (extracted_text, display_filename)."""
    creds = _get_credentials(owner_id)
    service = build("drive", "v3", credentials=creds)

    meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()
    filename = meta["name"]
    mime_type = meta["mimeType"]

    buffer = io.BytesIO()
    if mime_type in EXPORT_MIME_MAP:
        export_mime, ext = EXPORT_MIME_MAP[mime_type]
        request = service.files().export_media(fileId=file_id, mimeType=export_mime)
        filename = f"{filename}.{ext}"
    else:
        request = service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    data = buffer.getvalue()
    text = extract_text(filename, data)
    return text, filename
