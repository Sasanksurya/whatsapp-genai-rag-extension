import pytest

from app.mcp.security import UnsafeURLError, assert_safe_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/admin",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "ftp://example.com/file",
    ],
)
def test_blocks_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        assert_safe_url(url)


def test_allows_public_url():
    assert_safe_url("https://en.wikipedia.org/wiki/Python") is None
