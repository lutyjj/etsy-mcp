{
  description = "Read-only Etsy Open API v3 MCP server generated from Etsy's OpenAPI spec";

  inputs.nixpkgs.url = "https://channels.nixos.org/nixos-26.05/nixexprs.tar.xz";

  outputs =
    { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        etsy-mcp = pkgs.callPackage ./nix/package.nix { };
        default = etsy-mcp;
      });

      # Defaults the package rather than adding an overlay, which read-only
      # pkgs (nixpkgs.pkgs, runNixOSTest) would reject.
      nixosModules.default =
        { lib, pkgs, ... }:
        {
          imports = [ ./nix/module.nix ];
          services.etsy-mcp.package = lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
        };

      checks = lib.genAttrs [ "x86_64-linux" "aarch64-linux" ] (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          package = self.packages.${system}.default;
          # Boots the service as deployed and checks the MCP endpoint's contract:
          # health is open, /mcp refuses a wrong token and serves the right one.
          module = pkgs.testers.runNixOSTest {
            name = "etsy-mcp";
            nodes.machine = {
              imports = [ self.nixosModules.default ];
              environment.systemPackages = [ pkgs.curl ];
              environment.etc = {
                "etsy/keystring".text = "test-key";
                "etsy/secret".text = "test-secret";
                "etsy/auth-token".text = "test-token";
              };
              services.etsy-mcp = {
                enable = true;
                keystringFile = "/etc/etsy/keystring";
                secretFile = "/etc/etsy/secret";
                authTokenFile = "/etc/etsy/auth-token";
              };
            };
            testScript = ''
              init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}'
              curl = "curl -s -o /dev/null -w '%{http_code}' -H 'content-type: application/json' -H 'accept: application/json, text/event-stream'"
              machine.wait_for_unit("etsy-mcp.service")
              machine.wait_for_open_port(3737)
              machine.succeed("curl -sf http://127.0.0.1:3737/health")
              assert machine.succeed(f"{curl} -d '{init}' http://127.0.0.1:3737/mcp") == "401"
              assert machine.succeed(f"{curl} -H 'authorization: Bearer nope' -d '{init}' http://127.0.0.1:3737/mcp") == "401"
              assert machine.succeed(f"{curl} -H 'authorization: Bearer test-token' -d '{init}' http://127.0.0.1:3737/mcp") == "200"
            '';
          };
        }
      );

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (
              ps: with ps; [
                fastmcp
                httpx
                pytest
              ]
            ))
          ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
