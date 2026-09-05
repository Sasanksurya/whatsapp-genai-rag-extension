from app.agents.orchestrator import _has_strong_hit
from app.core.config import settings


def test_strong_hit_detected_below_threshold():
    hits = [{"text": "x", "metadata": {"filename": "f"}, "distance": 0.35}]
    assert _has_strong_hit(hits) is True


def test_weak_hit_not_detected_above_threshold():
    hits = [{"text": "x", "metadata": {"filename": "f"}, "distance": 1.4}]
    assert _has_strong_hit(hits) is False


def test_empty_hits_never_strong():
    assert _has_strong_hit([]) is False


def test_threshold_is_configurable():
    settings.relevance_distance_threshold = 0.1
    hits = [{"text": "x", "metadata": {"filename": "f"}, "distance": 0.35}]
    assert _has_strong_hit(hits) is False
