"""Token refresh behaviour against a fake Etsy token endpoint."""

import asyncio
import json
import time

import httpx2
import pytest

from etsy_mcp.auth import EtsyAuth, NotLoggedIn, TokenStore


def make(tmp_path, tokens, api_handler):
    store = TokenStore(tmp_path / "tokens.json")
    if tokens is not None:
        store.save(tokens)
    refreshes = []

    def token_handler(request):
        form = dict(x.split("=") for x in request.content.decode().split("&"))
        refreshes.append(form["refresh_token"])
        n = len(refreshes)
        return httpx2.Response(200, json={"access_token": f"a{n}", "refresh_token": f"r{n}", "expires_in": 3600})

    auth = EtsyAuth("key", "sec", store, httpx2.AsyncClient(transport=httpx2.MockTransport(token_handler)))
    api = httpx2.AsyncClient(transport=httpx2.MockTransport(api_handler), auth=auth, base_url="https://etsy.test")
    return store, api, refreshes


def ok(request):
    assert request.headers["x-api-key"] == "key:sec"
    return httpx2.Response(200, json={"bearer": request.headers["authorization"]})


def test_expired_token_refreshes_once_and_persists_rotation(tmp_path):
    store, api, refreshes = make(tmp_path, {"access_token": "old", "refresh_token": "r0", "expires_at": 0}, ok)

    async def run():
        return [(await api.get("/x")).json()["bearer"] for _ in range(3)]

    assert asyncio.run(run()) == ["Bearer a1"] * 3
    assert refreshes == ["r0"]
    saved = store.load()
    assert saved["refresh_token"] == "r1"
    assert saved["expires_at"] > time.time() + 3000


def test_concurrent_requests_share_one_refresh(tmp_path):
    _, api, refreshes = make(tmp_path, {"access_token": "old", "refresh_token": "r0", "expires_at": 0}, ok)

    async def run():
        return await asyncio.gather(*(api.get("/x") for _ in range(5)))

    asyncio.run(run())
    assert refreshes == ["r0"]


def test_rejected_fresh_token_is_refreshed_and_retried(tmp_path):
    def api_handler(request):
        if request.headers["authorization"] == "Bearer revoked":
            return httpx2.Response(401)
        return ok(request)

    tokens = {"access_token": "revoked", "refresh_token": "r0", "expires_at": time.time() + 3600}
    _, api, refreshes = make(tmp_path, tokens, api_handler)
    response = asyncio.run(api.get("/x"))
    assert response.json()["bearer"] == "Bearer a1"
    assert refreshes == ["r0"]


def test_missing_token_file_names_the_login_command(tmp_path):
    _, api, _ = make(tmp_path, None, ok)
    with pytest.raises(NotLoggedIn, match="etsy-mcp-login"):
        asyncio.run(api.get("/x"))


def test_token_file_is_private(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    store.save({"access_token": "a", "refresh_token": "r", "expires_at": 1})
    assert (store.path.stat().st_mode & 0o777) == 0o600
    assert json.loads(store.path.read_text())["refresh_token"] == "r"
