"""MCP server generated from Etsy's Open API v3 specification."""

from __future__ import annotations

import hmac
import json
import os
from collections.abc import Iterator
from importlib import resources

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.providers.openapi import MCPType, RouteMap
from fastmcp.server.transforms import Visibility
from starlette.requests import Request
from starlette.responses import JSONResponse

from .auth import EtsyAuth, TokenStore
from .config import Settings, ToolFilter, read_secret

# Every operation becomes a tool. Besides Etsy's own tags (`ShopListing`,
# `Shop Receipt`, ...), each carries one of these by HTTP method, so a filter
# can drop all writes or all deletes at once.
METHOD_TAGS = {
    "GET": "read",
    "POST": "write",
    "PUT": "write",
    "PATCH": "write",
    "DELETE": "delete",
}
ROUTES = [
    *(RouteMap(methods=[method], mcp_type=MCPType.TOOL, mcp_tags={tag}) for method, tag in METHOD_TAGS.items()),
    RouteMap(mcp_type=MCPType.EXCLUDE),
]


def load_spec() -> dict:
    return json.loads(
        resources.files("etsy_mcp").joinpath("etsy-openapi.json").read_text()
    )


def operations(spec: dict) -> Iterator[dict]:
    for path in spec["paths"].values():
        for method, op in path.items():
            if method.upper() in METHOD_TAGS:
                yield op


def oauth_scopes(op: dict) -> set[str]:
    return {scope for requirement in op.get("security", []) for scopes in requirement.values() for scope in scopes}


def apply_filter(mcp: FastMCP, spec: dict, tools: ToolFilter) -> None:
    names = {op["operationId"] for op in operations(spec)}
    tags = set(METHOD_TAGS.values()) | {tag for op in operations(spec) for tag in op.get("tags", [])}
    # A misspelt name would otherwise filter nothing, silently.
    unknown = sorted((tools.include_tools | tools.exclude_tools) - names) + sorted(
        (tools.include_tags | tools.exclude_tags) - tags
    )
    if unknown:
        raise SystemExit(f"Unknown tool or tag in the tool filter: {', '.join(unknown)}")

    # Later visibility transforms override earlier ones. FastMCP's enable()
    # matches names AND tags, so each include is its own transform.
    if tools.include_tools or tools.include_tags:
        mcp.add_transform(Visibility(False, match_all=True))
    if tools.include_tools:
        mcp.enable(names=set(tools.include_tools))
    if tools.include_tags:
        mcp.enable(tags=set(tools.include_tags))
    if tools.exclude_tools:
        mcp.disable(names=set(tools.exclude_tools))
    if tools.exclude_tags:
        mcp.disable(tags=set(tools.exclude_tags))


async def required_scopes(mcp: FastMCP, spec: dict) -> list[str]:
    """The OAuth scopes the exposed tools need, per Etsy's spec."""
    by_name = {op["operationId"]: oauth_scopes(op) for op in operations(spec)}
    return sorted(set().union(*(by_name[tool.name] for tool in await mcp.list_tools())))


class SharedTokenVerifier(TokenVerifier):
    """Accepts one static Bearer token, compared in constant time."""

    def __init__(self, token: str):
        super().__init__()
        self._token = token.encode()

    async def verify_token(self, token: str) -> AccessToken | None:
        if hmac.compare_digest(token.encode(), self._token):
            return AccessToken(token=token, client_id="etsy-mcp", scopes=[])
        return None


def build_server(
    settings: Settings,
    auth_token: str | None,
    tools: ToolFilter = ToolFilter(),
) -> FastMCP:
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
        route_maps=ROUTES,
        # Etsy's responses drift from its published schemas; strict output
        # validation would turn valid data into tool errors.
        validate_output=False,
        auth=SharedTokenVerifier(auth_token) if auth_token else None,
    )
    apply_filter(mcp, spec, tools)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    return mcp


def main() -> None:
    settings = Settings.from_env()
    auth_token = read_secret("ETSY_MCP_TOKEN_FILE") if os.environ.get("ETSY_MCP_TOKEN_FILE") else None
    if auth_token is None and os.environ.get("ETSY_MCP_ALLOW_NO_AUTH") != "1":
        raise SystemExit("ETSY_MCP_TOKEN_FILE is unset; set ETSY_MCP_ALLOW_NO_AUTH=1 for local use")
    build_server(settings, auth_token, ToolFilter.from_env()).run(
        transport="http",
        host=os.environ.get("ETSY_MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("ETSY_MCP_PORT", "3737")),
        path="/mcp",
    )
