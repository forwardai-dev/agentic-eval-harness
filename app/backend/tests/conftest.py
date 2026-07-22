"""Shared pytest fixtures: an isolated app state per test, a fresh TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aeh.api import app, state


@pytest.fixture(autouse=True)
def _isolated_state():
    """Every test gets a clean ledger/run-history and no disk persistence."""
    state.reset()
    state.out_dir = None
    yield
    state.reset()


@pytest.fixture()
def client() -> TestClient:
    """A TestClient bound to the shared app (no live server needed)."""
    return TestClient(app)
