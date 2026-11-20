{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.etsy-mcp;
  stateDir = "/var/lib/etsy-mcp";
  tokenFile = "${stateDir}/tokens.json";

  # The server reads the filter to expose its tools, and the login reads it
  # to request the scopes those tools need.
  filterEnv = lib.filterAttrs (_: value: value != "") {
    ETSY_MCP_INCLUDE_TOOLS = lib.concatStringsSep "," cfg.includeTools;
    ETSY_MCP_INCLUDE_TAGS = lib.concatStringsSep "," cfg.includeTags;
    ETSY_MCP_EXCLUDE_TOOLS = lib.concatStringsSep "," cfg.excludeTools;
    ETSY_MCP_EXCLUDE_TAGS = lib.concatStringsSep "," cfg.excludeTags;
  };

  filterOption =
    description:
    lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      inherit description;
    };

  # The consent flow is interactive, so it runs in the operator's shell as
  # root (which can read the credential files) and hands the result to the
  # service user.
  login = pkgs.writeShellScriptBin "etsy-mcp-login" ''
    set -euo pipefail
    if [ "$(id -u)" != 0 ]; then echo "run as root" >&2; exit 1; fi
    export ETSY_KEYSTRING_FILE=${lib.escapeShellArg cfg.keystringFile}
    export ETSY_SECRET_FILE=${lib.escapeShellArg cfg.secretFile}
    export ETSY_TOKEN_FILE=${tokenFile}
    ${lib.concatStrings (
      lib.mapAttrsToList (name: value: "export ${name}=${lib.escapeShellArg value}\n") filterEnv
    )}
    ${lib.getExe' cfg.package "etsy-mcp-login"} ${
      lib.optionalString (cfg.redirectUri != null) "--redirect-uri ${lib.escapeShellArg cfg.redirectUri}"
    } "$@"
    chown etsy-mcp:etsy-mcp ${tokenFile} ${tokenFile}.lock
  '';
in
{
  options.services.etsy-mcp = {
    enable = lib.mkEnableOption "the Etsy Open API v3 MCP server";
    package = lib.mkOption {
      type = lib.types.package;
      description = "The etsy-mcp package.";
    };
    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 3737;
    };
    keystringFile = lib.mkOption {
      type = lib.types.path;
      description = "File holding the Etsy app keystring.";
    };
    secretFile = lib.mkOption {
      type = lib.types.path;
      description = "File holding the Etsy app shared secret.";
    };
    authTokenFile = lib.mkOption {
      type = lib.types.path;
      description = "File holding the Bearer token MCP clients must send to /mcp.";
    };
    redirectUri = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "HTTPS redirect URI registered in the Etsy app, used by etsy-mcp-login.";
    };
    # Tool names are Etsy's operationIds. Tags are Etsy's (`ShopListing`,
    # `Shop Receipt`, ...) plus `read`, `write` and `delete` by HTTP method.
    includeTools = filterOption "Tools to expose. Any include makes the filter an allowlist; empty exposes every tool.";
    includeTags = filterOption "Expose the tools carrying any of these tags. Any include makes the filter an allowlist.";
    excludeTools = filterOption "Tools to hide. Excludes win over includes.";
    excludeTags = filterOption "Hide the tools carrying any of these tags. Excludes win over includes.";
  };

  config = lib.mkIf cfg.enable {
    users.users.etsy-mcp = {
      isSystemUser = true;
      group = "etsy-mcp";
      home = stateDir;
    };
    users.groups.etsy-mcp = { };

    environment.systemPackages = [ login ];

    systemd.services.etsy-mcp = {
      description = "Etsy MCP server";
      wantedBy = [ "multi-user.target" ];
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      environment = {
        ETSY_MCP_HOST = cfg.host;
        ETSY_MCP_PORT = toString cfg.port;
        ETSY_TOKEN_FILE = tokenFile;
        ETSY_KEYSTRING_FILE = "%d/keystring";
        ETSY_SECRET_FILE = "%d/secret";
        ETSY_MCP_TOKEN_FILE = "%d/auth-token";
      }
      // filterEnv;
      serviceConfig = {
        ExecStart = lib.getExe cfg.package;
        User = "etsy-mcp";
        Group = "etsy-mcp";
        StateDirectory = "etsy-mcp";
        StateDirectoryMode = "0700";
        LoadCredential = [
          "keystring:${cfg.keystringFile}"
          "secret:${cfg.secretFile}"
          "auth-token:${cfg.authTokenFile}"
        ];
        Restart = "on-failure";
        RestartSec = 5;
        CapabilityBoundingSet = "";
        LockPersonality = true;
        MemoryDenyWriteExecute = true;
        NoNewPrivileges = true;
        PrivateDevices = true;
        PrivateTmp = true;
        ProtectHome = true;
        ProtectSystem = "strict";
        RestrictAddressFamilies = [
          "AF_UNIX"
          "AF_INET"
          "AF_INET6"
        ];
        SystemCallFilter = [ "@system-service" ];
      };
    };
  };
}
