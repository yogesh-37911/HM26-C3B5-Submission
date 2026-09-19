"""Test fixtures.

The suite runs against a throwaway SQLite file seeded once per session with a
small synthetic dataset, so tests exercise the real query paths rather than
mocks.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, ROOT)

_DB_PATH = os.path.join(tempfile.gettempdir(), "civicpulse_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["JWT_SECRET"] = "test-secret-not-used-in-production"
os.environ["EVIDENCE_DIR"] = os.path.join(tempfile.gettempdir(), "civicpulse_test_evidence")


@pytest.fixture(scope="session", autouse=True)
def seeded():
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_DB_PATH + suffix)
        except FileNotFoundError:
            pass
    seed = os.path.join(REPO, "src", "scripts", "seed.py")
    result = subprocess.run(
        [sys.executable, seed, "--complaints", "150", "--reset"],
        capture_output=True, text=True, env={**os.environ},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return True


@pytest.fixture(scope="session")
def client(seeded):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c
