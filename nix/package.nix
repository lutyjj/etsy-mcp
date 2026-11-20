{ lib, python3Packages }:

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
  dependencies = with python3Packages; [
    fastmcp
    httpx
  ];
  nativeCheckInputs = [ python3Packages.pytestCheckHook ];

  meta = {
    description = "Read-only Etsy Open API v3 MCP server generated from Etsy's OpenAPI spec";
    mainProgram = "etsy-mcp";
  };
}
