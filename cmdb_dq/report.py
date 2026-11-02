from __future__ import annotations

import json
from collections import Counter

from .checks import Finding


def summarize(findings: list[Finding]) -> dict:
    return {
        "total": len(findings),
        "by_check": dict(Counter(f.check for f in findings).most_common()),
        "by_severity": dict(Counter(f.severity for f in findings).most_common()),
    }


def to_json(cis: list[dict], findings: list[Finding], score: float) -> str:
    return json.dumps({"ci_count": len(cis), "health_score": score, "summary": summarize(findings),
                       "findings": [f.to_dict() for f in findings]}, indent=2)


def to_markdown(cis: list[dict], findings: list[Finding], score: float) -> str:
    s = summarize(findings)
    lines = [
        "# CMDB Data Quality Report",
        "",
        f"- CIs evaluated: **{len(cis)}**",
        f"- Health score: **{score} / 100**",
        f"- Findings: **{s['total']}**",
        "",
        "## Findings by check",
        "",
        "| Check | Count |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in s["by_check"].items()]
    lines += ["", "## Detail", "", "| Severity | Check | CI | Class | Detail |", "|---|---|---|---|---|"]
    order = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(findings, key=lambda f: (order.get(f.severity, 9), f.check, f.ci_name)):
        lines.append(f"| {f.severity} | {f.check} | {f.ci_name or f.sys_id} | {f.ci_class} | {f.detail} |")
    return "\n".join(lines) + "\n"
