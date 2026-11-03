"""Score history: append one entry per run so CMDB health can be trended over time."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .checks import Finding
from .report import summarize


def append(path: str | Path, ci_count: int, score: float, findings: list[Finding]) -> dict:
    p = Path(path)
    history = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    previous = history[-1]["health_score"] if history else None
    entry = {"run_at": datetime.now(UTC).isoformat(timespec="seconds"), "ci_count": ci_count,
             "health_score": score, "delta": None if previous is None else round(score - previous, 1),
             "by_check": summarize(findings)["by_check"]}
    history.append(entry)
    p.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return entry
