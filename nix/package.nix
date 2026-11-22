{
  lib,
  callPackage,
  python3Packages,
}:
let
  fastmcp = callPackage ./fastmcp.nix { };
  # Release Please bumps the version in pyproject.toml alone.
  project = (lib.importTOML ../pyproject.toml).project;
in
python3Packages.buildPythonApplication {
  pname = project.name;
  inherit (project) version;
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../README.md
      ../LICENSE
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
    inherit (project) description;
    license = lib.licenses.mit;
    mainProgram = "etsy-mcp";
  };
}
