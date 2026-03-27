import importlib
from pathlib import Path
from typing import Any, Generator

import anyio
import httpx
import pytest


class SyncHttpxClient:
    """
    Synchronous wrapper around httpx.AsyncClient.

    httpx>=0.28 made ASGITransport async-only, which means using httpx.Client
    (sync client) with ASGITransport fails because the transport does not
    implement the sync context manager protocol (__enter__/__exit__).

    This wrapper lets the existing (sync) tests keep calling client.get/post/patch/delete
    while executing the underlying requests via anyio.run().

    Note: This is intentionally minimal, exposing only what the current tests use.
    """

    def __init__(self, async_client: httpx.AsyncClient):
        self._async_client = async_client

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """
        Execute an HTTP request synchronously against the underlying AsyncClient.

        Important:
          - anyio.run() only accepts positional args (and backend options).
          - Therefore we must not pass request kwargs (e.g. json=..., params=...)
            into anyio.run(). Instead, capture them in a closure and pass them
            to AsyncClient.request() from inside an async function.
        """

        async def _do_request() -> httpx.Response:
            return await self._async_client.request(method, url, **kwargs)

        return anyio.run(_do_request)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        """Close the underlying AsyncClient synchronously."""
        anyio.run(self._async_client.aclose)


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
def client(app) -> Generator[SyncHttpxClient, None, None]:
    """
    httpx client that calls the FastAPI app in-process via ASGITransport.

    Uses AsyncClient because ASGITransport is async-only in httpx==0.28.x, but
    exposes a sync API to tests via SyncHttpxClient.
    """
    transport = httpx.ASGITransport(app=app)

    async_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    sync_client = SyncHttpxClient(async_client)

    try:
        yield sync_client
    finally:
        sync_client.close()
