import os
import requests

from dotenv import load_dotenv
from fastapi import HTTPException

# -----------------------------
# Load .env automatically
# -----------------------------
load_dotenv()

NODE_BACKEND_URL = os.getenv("NODE_BACKEND_URL", "http://localhost:5000")
NODE_INTERNAL_SECRET = os.getenv("NODE_INTERNAL_SECRET")


def verify_conversation_membership(conversation_id: str, user_id: str):
    """
    Verify that the given user belongs to the given WhatsApp conversation
    by calling the Node.js internal verification API.
    """

    if not NODE_INTERNAL_SECRET:
        raise HTTPException(
            status_code=500,
            detail="NODE_INTERNAL_SECRET is not configured on the GenAI backend."
        )

    url = (
        f"{NODE_BACKEND_URL}"
        f"/api/internal/connections/{conversation_id}/verify"
    )

    headers = {
        "X-Internal-Secret": NODE_INTERNAL_SECRET
    }

    params = {
        "userId": user_id
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=10
        )

    except requests.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to Node backend: {str(e)}"
        )

    if response.status_code == 200:
        data = response.json()

        if data.get("authorized") is True:
            return data

    if response.status_code == 403:
        raise HTTPException(
            status_code=403,
            detail="User is not a member of this conversation."
        )

    if response.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Internal authentication failed."
        )

    raise HTTPException(
        status_code=response.status_code,
        detail=response.text
    )