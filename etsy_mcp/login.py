"""One-time OAuth consent (authorization code + PKCE) that writes the token file.

Etsy redirects the browser to the app's registered HTTPS redirect URI with
`code` and `state` in the query. That page need not exist: paste the URL
from the address bar back here.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2

from .auth import TOKEN_URL, TokenStore, tokens_from_response
from .config import Settings, ToolFilter
from .server import build_server, load_spec, required_scopes

AUTHORIZE_URL = "https://www.etsy.com/oauth/connect"


def main() -> None:
    parser = argparse.ArgumentParser(prog="etsy-mcp-login", description=__doc__)
    parser.add_argument("--redirect-uri", required=True, help="HTTPS URI registered in the Etsy app")
    parser.add_argument(
        "--scopes",
        help="space-separated OAuth scopes; default: what the tools the ETSY_MCP_* filter exposes need",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.scopes is None:
        server = build_server(settings, auth_token=None, tools=ToolFilter.from_env())
        args.scopes = " ".join(asyncio.run(required_scopes(server, load_spec())))
    if not args.scopes:
        # Etsy's consent screen needs at least one scope.
        sys.exit("The exposed tools need no OAuth scopes; pass --scopes to log in anyway")
    print(f"Requesting scopes: {args.scopes}")
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.keystring,
            "redirect_uri": args.redirect_uri,
            "scope": args.scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    print(f"Open this URL, approve, then paste the URL you land on:\n\n{AUTHORIZE_URL}?{query}\n")
    returned = parse_qs(urlsplit(input("Redirected URL: ").strip()).query)
    if returned.get("state", [None])[0] != state:
        sys.exit("State mismatch; start again")
    if "code" not in returned:
        sys.exit(f"No code in the URL: {returned.get('error', ['unknown error'])[0]}")

    response = httpx2.post(
        TOKEN_URL,
        headers={"x-api-key": f"{settings.keystring}:{settings.secret}"},
        data={
            "grant_type": "authorization_code",
            "client_id": settings.keystring,
            "redirect_uri": args.redirect_uri,
            "code": returned["code"][0],
            "code_verifier": verifier,
        },
        timeout=30,
    )
    if response.status_code != 200:
        sys.exit(f"Token exchange failed: HTTP {response.status_code} {response.text[:200]}")
    store = TokenStore(settings.token_file)
    with store.locked():
        store.save(tokens_from_response(response.json()))
    print(f"Saved tokens to {settings.token_file}")
