"""Which tools the generated server exposes, and the OAuth scopes they need."""

import asyncio
import time
from urllib.parse import parse_qs

import httpx2
import pytest
from fastmcp.exceptions import NotFoundError

from etsy_mcp.auth import TokenStore
from etsy_mcp.config import Settings, ToolFilter
from etsy_mcp.server import build_server, load_spec, required_scopes


def server(tmp_path, **tools):
    filter_ = ToolFilter(**{key: frozenset(value) for key, value in tools.items()})
    return build_server(Settings("key", "sec", tmp_path / "tokens.json"), auth_token="t", tools=filter_)


def tools(mcp):
    return {tool.name: tool.tags for tool in asyncio.run(mcp.list_tools())}


def test_every_operation_is_a_tool_tagged_by_method(tmp_path):
    spec = load_spec()
    operations = {op["operationId"] for path in spec["paths"].values() for op in path.values()}

    exposed = tools(server(tmp_path))

    assert set(exposed) == operations
    assert {"read", "Shop"} <= exposed["getShop"]
    assert {"write", "ShopListing"} <= exposed["updateListing"]
    assert {"delete", "ShopListing"} <= exposed["deleteListing"]


def test_descriptions_drop_release_badges_but_keep_other_notices(tmp_path):
    described = {tool.name: tool.description for tool in asyncio.run(server(tmp_path).list_tools())}

    assert not [name for name, text in described.items() if "<div" in (text or "")]
    assert described["getMe"].startswith("Returns basic info for the user making the request.")
    assert described["getListingProperty"].startswith(
        "Development for this endpoint is in progress. It will only return a 501 response."
    )


def test_write_tools_send_the_body_encoding_the_spec_declares(tmp_path):
    # Etsy declares application/x-www-form-urlencoded for updateListing and
    # rejects JSON bodies on such endpoints.
    TokenStore(tmp_path / "tokens.json").save(
        {"access_token": "a", "refresh_token": "r", "expires_at": time.time() + 3600}
    )
    sent = []

    def etsy(request):
        sent.append(request)
        return httpx2.Response(200, json={"listing_id": 2})

    mcp = build_server(
        Settings("key", "sec", tmp_path / "tokens.json"),
        auth_token="t",
        transport=httpx2.MockTransport(etsy),
    )
    asyncio.run(
        mcp.call_tool("updateListing", {"shop_id": 1, "listing_id": 2, "title": "Frame", "should_auto_renew": True})
    )

    [request] = sent
    assert (request.method, request.url.path) == ("PATCH", "/v3/application/shops/1/listings/2")
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert parse_qs(request.content.decode()) == {"title": ["Frame"], "should_auto_renew": ["true"]}
    assert request.headers["authorization"] == "Bearer a"


def test_includes_are_a_union_and_excludes_win(tmp_path):
    mcp = server(
        tmp_path,
        include_tools={"ping"},
        include_tags={"Review"},
        exclude_tools={"getReviewsByShop"},
    )
    assert set(tools(mcp)) == {"ping", "getReviewsByListing"}


def test_excluding_by_tag_drops_writes(tmp_path):
    exposed = tools(server(tmp_path, exclude_tags={"write", "delete"}))
    assert "getShop" in exposed
    assert not {"updateListing", "deleteListing"} & set(exposed)


def test_excluded_tool_cannot_be_called(tmp_path):
    mcp = server(tmp_path, exclude_tools={"ping"})
    with pytest.raises(NotFoundError):
        asyncio.run(mcp.call_tool("ping", {}))


def test_unknown_filter_name_fails_at_start(tmp_path):
    with pytest.raises(SystemExit, match="getShopp"):
        server(tmp_path, exclude_tools={"getShopp"})


def test_login_scopes_follow_the_exposed_tools(tmp_path):
    spec = load_spec()
    # Listing images are read with the API key alone; uploading and deleting
    # one needs listings_w.
    images = server(tmp_path, include_tags={"ShopListing Image"})
    images_read_only = server(tmp_path, include_tags={"ShopListing Image"}, exclude_tags={"write", "delete"})

    assert asyncio.run(required_scopes(images, spec)) == ["listings_w"]
    assert asyncio.run(required_scopes(images_read_only, spec)) == []
