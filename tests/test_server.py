"""Which tools the generated server exposes, and the OAuth scopes they need."""

import asyncio

import pytest
from fastmcp.exceptions import NotFoundError

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
