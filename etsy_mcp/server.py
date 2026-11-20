"""Read-only MCP server generated from Etsy's Open API v3 specification."""

from __future__ import annotations

import hmac
import json
import os
from importlib import resources

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.providers.openapi import MCPType, RouteMap
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import EtsyAuth, TokenStore
from .config import Settings, read_secret

# Every GET becomes a tool; nothing else exists, so the server cannot write
# even if the OAuth grant someday carries write scopes.
READ_ONLY_ROUTES = [
    RouteMap(methods=["GET"], mcp_type=MCPType.TOOL),
    RouteMap(mcp_type=MCPType.EXCLUDE),
]


def load_spec() -> dict:
    return json.loads(
        resources.files("etsy_mcp").joinpath("etsy-openapi.json").read_text()
    )


class SharedTokenVerifier(TokenVerifier):
    """Accepts one static Bearer token, compared in constant time."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token.encode()

    async def verify_token(self, token: str) -> AccessToken | None:
        if hmac.compare_digest(token.encode(), self._token):
            return AccessToken(token=token, client_id="etsy-mcp", scopes=[])
        return None


def build_server(settings: Settings, auth_token: str | None) -> FastMCP:
    spec = load_spec()
    client = httpx.AsyncClient(
        base_url=spec["servers"][0]["url"],
        auth=EtsyAuth(settings.keystring, settings.secret, TokenStore(settings.token_file)),
        timeout=30,
    )
    mcp = FastMCP.from_openapi(
        openapi_spec=spec,
        client=client,
        name="Etsy",
        route_maps=READ_ONLY_ROUTES,
        # Etsy's responses drift from its published schemas; strict output
        # validation would turn valid data into tool errors.
        validate_output=False,
        auth=SharedTokenVerifier(auth_token) if auth_token else None,
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    return mcp


def main() -> None:
    settings = Settings.from_env()
    auth_token = read_secret("ETSY_MCP_TOKEN_FILE") if os.environ.get("ETSY_MCP_TOKEN_FILE") else None
    if auth_token is None and os.environ.get("ETSY_MCP_ALLOW_NO_AUTH") != "1":
        raise SystemExit("ETSY_MCP_TOKEN_FILE is unset; set ETSY_MCP_ALLOW_NO_AUTH=1 for local use")
    build_server(settings, auth_token).run(
        transport="http",
        host=os.environ.get("ETSY_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("ETSY_MCP_PORT", "3737")),
        path="/mcp",
    )
