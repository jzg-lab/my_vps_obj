"""Unit tests must opt in to Redis instead of inheriting CI's live connection."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_redis_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep integration tests' Redis and explicit per-test settings untouched.
    monkeypatch.setenv("REDIS_URL", "")
