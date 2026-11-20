# etsy-mcp

A read-only MCP server for the Etsy Open API v3. FastMCP generates its tools from Etsy's published OpenAPI spec ([etsy-openapi.json](etsy_mcp/etsy-openapi.json)). Every GET operation becomes a tool; no other operation exists, so the server cannot write.

## Settings

All settings come from environment variables. Secrets are file paths, never values.

| Variable | Meaning |
| --- | --- |
| `ETSY_KEYSTRING_FILE` | Etsy app keystring |
| `ETSY_SECRET_FILE` | Etsy app shared secret |
| `ETSY_TOKEN_FILE` | Etsy OAuth token file, written by `etsy-mcp-login` and refreshed by the server (default `tokens.json`) |
| `ETSY_MCP_TOKEN_FILE` | Bearer token MCP clients send to `/mcp` |
| `ETSY_MCP_HOST`, `ETSY_MCP_PORT` | Listen address (default `127.0.0.1:3737`) |

The server serves Streamable HTTP at `/mcp` and an open `/health`.

## Log in to Etsy

Etsy access tokens last an hour, and each refresh replaces the refresh token. The server refreshes under a file lock and saves the new pair before using it, so the token file stays the only copy.

Run the consent flow once with an HTTPS redirect URI that is registered in the Etsy app:

```sh
etsy-mcp-login --redirect-uri https://example.com/callback
```

Open the printed URL, approve, and paste the URL the browser lands on. The page itself does not need to exist.

On NixOS, the module installs an `etsy-mcp-login` wrapper. Run it as root, and it hands the token file to the service user.

## Update the spec

```sh
curl -sL https://www.etsy.com/openapi/generated/oas/3.0.0.json -o etsy_mcp/etsy-openapi.json
```

## Develop

```sh
nix develop -c python -m pytest -q
nix build .#checks.x86_64-linux.module   # NixOS VM test of the module
```
