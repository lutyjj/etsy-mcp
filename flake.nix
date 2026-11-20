{
  description = "Etsy Open API v3 MCP server generated from Etsy's OpenAPI spec";

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
          # health is open, /mcp refuses a wrong token and serves the right one,
          # and the module's tool filter reaches both the server and the login.
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
                includeTools = [ "getShopReceipts" ];
                includeTags = [ "Review" ];
                excludeTools = [ "getReviewsByShop" ];
              };
            };
            testScript = ''
              import json

              url = "http://127.0.0.1:3737/mcp"
              init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}'
              headers = "-H 'content-type: application/json' -H 'accept: application/json, text/event-stream'"
              status = f"curl -s -o /dev/null -w '%{{http_code}}' {headers}"
              machine.wait_for_unit("etsy-mcp.service")
              machine.wait_for_open_port(3737)
              machine.succeed("curl -sf http://127.0.0.1:3737/health")
              assert machine.succeed(f"{status} -d '{init}' {url}") == "401"
              assert machine.succeed(f"{status} -H 'authorization: Bearer nope' -d '{init}' {url}") == "401"
              assert machine.succeed(f"{status} -H 'authorization: Bearer test-token' -d '{init}' {url}") == "200"

              # One MCP session: initialize, then list the tools the filter left.
              session = f"curl -sf {headers} -H 'authorization: Bearer test-token'"
              machine.succeed(f"{session} -D /tmp/headers -d '{init}' {url}")
              sid = machine.succeed("sed -n 's/^mcp-session-id: *//Ip' /tmp/headers | tr -d '\\r\\n'")
              session += f" -H 'mcp-session-id: {sid}'"
              machine.succeed(f"""{session} -d '{{"jsonrpc":"2.0","method":"notifications/initialized"}}' {url}""")
              listed = machine.succeed(f"""{session} -d '{{"jsonrpc":"2.0","id":2,"method":"tools/list"}}' {url}""")
              body = next((line[5:] for line in listed.splitlines() if line.startswith("data:")), listed)
              names = sorted(tool["name"] for tool in json.loads(body)["result"]["tools"])
              assert names == ["getReviewsByListing", "getShopReceipts"], names

              # The login asks for the scopes of those tools alone; it then
              # stops at the empty redirect URL.
              login = machine.fail("echo | etsy-mcp-login --redirect-uri https://example.com/callback 2>&1")
              assert "Requesting scopes: transactions_r\n" in login, login
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
