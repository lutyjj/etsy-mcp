"""The generated server exposes Etsy's read operations and nothing else."""

import asyncio

from etsy_mcp.config import Settings
from etsy_mcp.server import build_server, load_spec


def test_tools_are_exactly_the_get_operations(tmp_path):
    spec = load_spec()
    gets = {op["operationId"] for path in spec["paths"].values() for m, op in path.items() if m == "get"}
    writes = {op["operationId"] for path in spec["paths"].values() for m, op in path.items() if m != "get"}

    mcp = build_server(Settings("key", "sec", tmp_path / "tokens.json"), auth_token="t")
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}

    assert names == gets
    assert not names & writes
