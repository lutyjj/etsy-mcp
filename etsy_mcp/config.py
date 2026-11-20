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
