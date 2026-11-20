# etsy-mcp

An MCP server for the Etsy Open API v3. FastMCP generates its tools from Etsy's published OpenAPI spec ([etsy-openapi.json](etsy_mcp/etsy-openapi.json)). Every operation becomes a tool named by its `operationId`, and a filter decides which ones the server exposes.

## Settings

All settings come from environment variables. Secrets are file paths, never values.

| Variable | Meaning |
| --- | --- |
| `ETSY_KEYSTRING_FILE` | Etsy app keystring |
| `ETSY_SECRET_FILE` | Etsy app shared secret |
| `ETSY_TOKEN_FILE` | Etsy OAuth token file, written by `etsy-mcp-login` and refreshed by the server (default `tokens.json`) |
| `ETSY_MCP_TOKEN_FILE` | Bearer token MCP clients send to `/mcp` |
| `ETSY_MCP_HOST`, `ETSY_MCP_PORT` | Listen address (default `127.0.0.1:3737`) |
| `ETSY_MCP_INCLUDE_TOOLS`, `ETSY_MCP_INCLUDE_TAGS` | Comma-separated tools or tags to expose (default: every tool) |
| `ETSY_MCP_EXCLUDE_TOOLS`, `ETSY_MCP_EXCLUDE_TAGS` | Comma-separated tools or tags to hide |

The server serves Streamable HTTP at `/mcp` and an open `/health`.

## Choose the tools

Each tool carries Etsy's tags for its operation, such as `ShopListing` or `Shop Receipt`, and one tag for its HTTP method: `read` (GET), `write` (POST, PUT, PATCH) or `delete` (DELETE).

With no include set, the server exposes every tool. Any include turns the filter into an allowlist, and a tool stays if its name or one of its tags is included. Excludes then hide tools and win over includes. A name or tag that the spec does not have stops the server at start.

For example, `ETSY_MCP_EXCLUDE_TAGS=delete` exposes everything except deletes, and `ETSY_MCP_EXCLUDE_TAGS=write,delete` makes the server read-only. The method tag follows the HTTP method alone, so `tokenScopes`, a POST that only reads the token's grant, counts as `write`.

The NixOS module has the same four lists as options: `includeTools`, `includeTags`, `excludeTools` and `excludeTags`.

## Log in to Etsy

Etsy access tokens last an hour, and each refresh replaces the refresh token. The server refreshes under a file lock and saves the new pair before using it, so the token file stays the only copy.

Run the consent flow once with an HTTPS redirect URI that is registered in the Etsy app:

```sh
etsy-mcp-login --redirect-uri https://example.com/callback
```

It requests the OAuth scopes that the exposed tools need according to Etsy's spec, so it reads the same `ETSY_MCP_*` filter as the server. `--scopes` overrides them. After the filter changes, log in again if the new tools need scopes the old login did not grant; until then Etsy answers those tools with 403.

Open the printed URL, approve, and paste the URL the browser lands on. The page itself does not need to exist.

On NixOS, the module installs an `etsy-mcp-login` wrapper that carries the module's filter. Run it as root, and it hands the token file to the service user.

## Update the spec

```sh
curl -sL https://www.etsy.com/openapi/generated/oas/3.0.0.json -o etsy_mcp/etsy-openapi.json
```

## Develop

```sh
nix develop -c python -m pytest -q
nix build .#checks.x86_64-linux.module   # NixOS VM test of the module
```
