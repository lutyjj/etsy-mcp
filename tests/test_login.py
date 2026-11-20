"""etsy-mcp-login asks Etsy for the scopes of the tools the filter exposes."""

import sys

import pytest

from etsy_mcp import login


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("keystring", "secret"):
        (tmp_path / name).write_text("x")
        monkeypatch.setenv(f"ETSY_{name.upper()}_FILE", str(tmp_path / name))
    monkeypatch.setenv("ETSY_TOKEN_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setattr(sys, "argv", ["etsy-mcp-login", "--redirect-uri", "https://example.com/callback"])
    # The consent URL comes back with another state, so the login stops there.
    monkeypatch.setattr("builtins.input", lambda _: "https://example.com/callback?state=other&code=c")
    return monkeypatch


def test_requests_the_scopes_of_the_filtered_tools(env, capsys):
    env.setenv("ETSY_MCP_INCLUDE_TAGS", "Shop Receipt")
    env.setenv("ETSY_MCP_EXCLUDE_TAGS", "write")

    with pytest.raises(SystemExit, match="State mismatch"):
        login.main()

    out = capsys.readouterr().out
    assert "Requesting scopes: transactions_r\n" in out
    assert "scope=transactions_r&" in out


def test_stops_when_no_exposed_tool_needs_a_scope(env, capsys):
    env.setenv("ETSY_MCP_INCLUDE_TOOLS", "ping")

    with pytest.raises(SystemExit, match="need no OAuth scopes"):
        login.main()

    assert "oauth/connect" not in capsys.readouterr().out
