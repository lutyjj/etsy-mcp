{
  lib,
  callPackage,
  python3Packages,
}:
let
  fastmcp = callPackage ./fastmcp.nix { };
in
python3Packages.buildPythonApplication {
  pname = "etsy-mcp";
  version = "0.1.0";
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../etsy_mcp
      ../tests
    ];
  };

  build-system = [ python3Packages.setuptools ];
  dependencies = [
    fastmcp
    python3Packages.httpx2
  ]
  ++ fastmcp.optional-dependencies.server;
  nativeCheckInputs = [ python3Packages.pytestCheckHook ];

  passthru = { inherit fastmcp; };

  meta = {
    description = "Etsy Open API v3 MCP server generated from Etsy's OpenAPI spec";
    mainProgram = "etsy-mcp";
  };
}
