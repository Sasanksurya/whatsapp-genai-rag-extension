import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _reset_settings():
    """Prevent one test's settings mutation from leaking into another."""
    original = settings.model_dump()
    yield
    for key, value in original.items():
        setattr(settings, key, value)
