# FastMCP 4, until nixpkgs ships it (NixOS/nixpkgs#563493). nixpkgs-unstable
# has fastmcp-slim 3.4.7, marked broken against mcp 2; FastMCP 4 runs on mcp 2
# and httpx2, and its OpenAPI tools encode form and multipart bodies as the
# spec declares, which Etsy's write operations need. Delete this file, and use
# python3Packages.fastmcp-slim, once that is at 4.2 or later.
{ fetchFromGitHub, python3Packages }:

python3Packages.fastmcp-slim.overridePythonAttrs (old: rec {
  version = "4.2.3";
  src = fetchFromGitHub {
    owner = "PrefectHQ";
    repo = "fastmcp";
    tag = "v${version}";
    hash = "sha256-96PHLL5WKRF2BJ8zDZ8RRuE5TEx4ieafcOuaKKdSpKI=";
  };
  sourceRoot = "${src.name}/fastmcp_slim";
  # The 3.4.7 backport is upstream in 4.x.
  patches = [ ];
  # authlib, joserfc, openapi-pydantic, opentelemetry-api and py-key-value-aio
  # are a patch release or two below 4.2.3's floors on unstable.
  pythonRelaxDeps = true;
  dependencies = old.dependencies ++ [ python3Packages.mcp-types ];
  optional-dependencies = old.optional-dependencies // {
    mcp = with python3Packages; [
      exceptiongroup
      httpx2
      mcp
      opentelemetry-api
      starlette
    ];
  };
  # Its install check probes a 3.4.7 internal.
  doInstallCheck = false;
  meta = old.meta // {
    broken = false;
  };
})
