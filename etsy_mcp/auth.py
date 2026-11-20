"""Etsy Open API v3 authentication: API key header plus a rotating OAuth token.

Etsy access tokens live one hour, and every refresh returns a new refresh
token that invalidates the old one. The token file is therefore the single
source of truth, shared by the server and the login command, and every
refresh happens under an exclusive file lock after re-reading it.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import time
from collections.abc import AsyncGenerator
from contextlib import contextmanager
from pathlib import Path

import httpx

TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
# Refresh this long before Etsy's stated expiry so a request never races it.
EXPIRY_MARGIN_SECONDS = 120


class NotLoggedIn(RuntimeError):
    pass


class TokenStore:
    """JSON token file written atomically with mode 0600, locked by a sibling file."""

    def __init__(self, path: Path):
        self.path = path
        self._lock_path = path.with_name(path.name + ".lock")

    @contextmanager
    def locked(self):
        fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return None

    def save(self, tokens: dict) -> None:
        tmp = self.path.with_name(f"{self.path.name}.tmp.{os.getpid()}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(tokens, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)


def tokens_from_response(payload: dict, now: float | None = None) -> dict:
    """What we keep from a token endpoint response; expires_at is absolute."""
    now = time.time() if now is None else now
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": now + int(payload["expires_in"]),
    }


class EtsyAuth(httpx.Auth):
    """Adds `x-api-key` and a fresh Bearer token; refreshes once on a 401."""

    def __init__(
        self,
        keystring: str,
        secret: str,
        store: TokenStore,
        token_client: httpx.AsyncClient | None = None,
    ):
        self._api_key = f"{keystring}:{secret}"
        self._client_id = keystring
        self._store = store
        self._token_client = token_client or httpx.AsyncClient(timeout=30)
        self._lock = asyncio.Lock()

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        token = await self._access_token()
        self._sign(request, token)
        response = yield request
        if response.status_code == 401:
            token = await self._access_token(rejected=token)
            self._sign(request, token)
            yield request

    def _sign(self, request: httpx.Request, token: str) -> None:
        request.headers["x-api-key"] = self._api_key
        request.headers["authorization"] = f"Bearer {token}"

    async def _access_token(self, rejected: str | None = None) -> str:
        async with self._lock:
            with self._store.locked():
                tokens = self._store.load()
                if not tokens or not tokens.get("refresh_token"):
                    raise NotLoggedIn(
                        f"No Etsy OAuth tokens in {self._store.path}; run etsy-mcp-login"
                    )
                current = tokens["access_token"]
                fresh = tokens["expires_at"] - EXPIRY_MARGIN_SECONDS > time.time()
                # Another process may have refreshed since the token was rejected.
                if current and current != rejected and fresh:
                    return current
                tokens = await self._refresh(tokens["refresh_token"])
                self._store.save(tokens)
                return tokens["access_token"]

    async def _refresh(self, refresh_token: str) -> dict:
        response = await self._token_client.post(
            TOKEN_URL,
            headers={"x-api-key": self._api_key},
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "refresh_token": refresh_token,
            },
        )
        if response.status_code != 200:
            # The body names the OAuth error only; it never echoes tokens.
            raise RuntimeError(
                f"Etsy token refresh failed: HTTP {response.status_code} {response.text[:200]}"
            )
        return tokens_from_response(response.json())
