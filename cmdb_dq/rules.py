"""Rule configuration loaded from TOML (stdlib tomllib, Python 3.11+)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("rules") / "default.toml"
VALID_SEVERITIES = {"high", "medium", "low"}


class RulesError(ValueError):
    pass


@dataclass(frozen=True)
class Rules:
    stale_days: int = 30
    discoverable_classes: tuple[str, ...] = ()
    orphan_exempt_classes: tuple[str, ...] = ()
    required_fields: dict[str, list[str]] = field(default_factory=dict)
    checks: dict[str, dict] = field(default_factory=dict)

    def enabled(self, name: str) -> bool:
        return bool(self.checks.get(name, {}).get("enabled", True))

    def severity(self, name: str) -> str:
        return self.checks.get(name, {}).get("severity", "medium")


def load_rules(path: str | Path | None = None) -> Rules:
    p = Path(path) if path else DEFAULT_PATH
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RulesError(f"rules file not found: {p}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RulesError(f"{p}: invalid TOML: {exc}") from exc

    stale = data.get("stale_days", 30)
    if not isinstance(stale, int) or stale <= 0:
        raise RulesError("stale_days must be a positive integer")
    checks = data.get("checks", {})
    for name, cfg in checks.items():
        if cfg.get("severity", "medium") not in VALID_SEVERITIES:
            raise RulesError(f"checks.{name}.severity must be one of {sorted(VALID_SEVERITIES)}")
    return Rules(stale_days=stale,
                 discoverable_classes=tuple(data.get("discoverable_classes", [])),
                 orphan_exempt_classes=tuple(data.get("orphan_exempt_classes", [])),
                 required_fields=dict(data.get("required_fields", {})),
                 checks=checks)


@lru_cache(maxsize=1)
def default_rules() -> Rules:
    return load_rules(DEFAULT_PATH)
