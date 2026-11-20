"""Settings from the environment. Secrets arrive as file paths, never values."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def read_secret(var: str) -> str:
    path = os.environ.get(var)
    if not path:
        raise SystemExit(f"{var} must name a file")
    value = Path(path).read_text().strip()
    if not value:
        raise SystemExit(f"{var} names an empty file")
    return value


def read_list(var: str) -> frozenset[str]:
    """A comma-separated variable; unset or empty is the empty set."""
    return frozenset(item.strip() for item in os.environ.get(var, "").split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    keystring: str
    secret: str
    token_file: Path

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            keystring=read_secret("ETSY_KEYSTRING_FILE"),
            secret=read_secret("ETSY_SECRET_FILE"),
            token_file=Path(os.environ.get("ETSY_TOKEN_FILE", "tokens.json")),
        )


@dataclass(frozen=True)
class ToolFilter:
    """Which tools the server exposes, by tool name (Etsy's operationId) or tag.

    With no includes, every tool is exposed. Any include turns the filter into
    an allowlist: a tool stays if its name or one of its tags is included.
    Excludes then remove tools by name or tag, and win over includes.
    """

    include_tools: frozenset[str] = frozenset()
    include_tags: frozenset[str] = frozenset()
    exclude_tools: frozenset[str] = frozenset()
    exclude_tags: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls) -> ToolFilter:
        return cls(
            include_tools=read_list("ETSY_MCP_INCLUDE_TOOLS"),
            include_tags=read_list("ETSY_MCP_INCLUDE_TAGS"),
            exclude_tools=read_list("ETSY_MCP_EXCLUDE_TOOLS"),
            exclude_tags=read_list("ETSY_MCP_EXCLUDE_TAGS"),
        )
