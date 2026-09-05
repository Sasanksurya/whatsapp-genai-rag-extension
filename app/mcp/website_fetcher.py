"""
Website fetching for the MCP Agent (project spec section 8).

Uses trafilatura for extraction because raw HTML->text via a naive
parser pulls in nav bars, ads, cookie banners, etc. — trafilatura is
tuned specifically for "give me the article/content, not the chrome."
"""
import httpx
import trafilatura

from app.mcp.security import assert_safe_url

MAX_CONTENT_BYTES = 5_000_000  # 5MB cap — don't let one URL blow the context/DB


class FetchError(Exception):
    pass


def fetch_url_text(url: str) -> str:
    assert_safe_url(url)

    try:
        response = httpx.get(
            url,
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "WhatsAppGenAIExtension/1.0 (+MCP website fetch)"},
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise FetchError(f"Failed to fetch '{url}': {e}")

    if len(response.content) > MAX_CONTENT_BYTES:
        raise FetchError(f"Content at '{url}' exceeds {MAX_CONTENT_BYTES} byte limit.")

    # Re-validate after following redirects — the final URL could differ
    # from what the user gave us (redirect-based SSRF bypass)
    final_url = str(response.url)
    if final_url != url:
        assert_safe_url(final_url)

    text = trafilatura.extract(response.text, url=final_url)
    if not text or not text.strip():
        raise FetchError(f"No extractable content found at '{url}'.")

    return text
