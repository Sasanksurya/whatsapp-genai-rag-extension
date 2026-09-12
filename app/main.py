from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.routes_auth import router as auth_router
from app.api.routes_documents import router as documents_router
from app.api.routes_converse import router as converse_router
from app.api.routes_mcp import router as mcp_router
from app.api.routes_voice import router as voice_router
from app.api.routes_whatsapp import router as whatsapp_router
from app.api.routes_twilio import router as twilio_router
from app.core.security_headers import SecurityHeadersMiddleware

app = FastAPI(
    title="WhatsApp GenAI Extension — Backend",
    description=(
        "Secure Multi-Agent GenAI + RAG + MCP backend. Not WhatsApp itself — "
        "designed to connect via an official WhatsApp/Meta integration later."
    ),
    version="0.6.0",
)

# Demo-only CORS: the prototype chat interface is served as static files
# from this same app, so this is mainly for convenience if you open the
# static files separately during development. Lock this down to real
# origins before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(converse_router, prefix="/api/v1")
app.include_router(mcp_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(whatsapp_router, prefix="/api/v1")
app.include_router(twilio_router, prefix="/api/v1")

app.mount("/demo", StaticFiles(directory="static", html=True), name="demo")


@app.get("/")
def root():
    return {"service": "whatsapp-genai-backend", "status": "running", "demo_ui": "/demo"}
