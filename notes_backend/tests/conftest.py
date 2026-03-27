import importlib
from pathlib import Path
from typing import Generator

import httpx
import pytest


@pytest.fixture()
def sqlite_db_path(tmp_path: Path) -> str:
    """
    Provide a per-test sqlite DB file path.

    Using a file (not in-memory) keeps behavior consistent across multiple connections.
    """
    return str(tmp_path / "test.db")


@pytest.fixture()
def app(monkeypatch: pytest.MonkeyPatch, sqlite_db_path: str):
    """
    Create a fresh FastAPI app wired to a temporary SQLite DB.

    The production app module (`src.api.main`) creates global singletons (db, flow)
    at import time based on environment variables. We therefore:
      1) set SQLITE_DB for this test
      2) reload the module so its globals bind to the temp DB
    """
    monkeypatch.setenv("SQLITE_DB", sqlite_db_path)
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")

    main_mod = importlib.import_module("src.api.main")
    main_mod = importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture()
def client(app) -> Generator[httpx.Client, None, None]:
    """
    httpx client that calls the FastAPI app in-process via ASGITransport.
    """
    transport = httpx.ASGITransport(app=app)
    with httpx.Client(transport=transport, base_url="http://testserver") as c:
        yield c
