"""Report writers: Markdown, JSON, self-contained HTML, and a remediation CSV."""
from __future__ import annotations

import csv
import html
import io
import json
from collections import Counter
from datetime import UTC, datetime

from .checks import Finding, score_by_class

ORDER = {"high": 0, "medium": 1, "low": 2}


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (ORDER.get(f.severity, 9), f.check, f.ci_name))


def summarize(findings: list[Finding]) -> dict:
    return {
        "total": len(findings),
        "by_check": dict(Counter(f.check for f in findings).most_common()),
        "by_severity": dict(Counter(f.severity for f in findings).most_common()),
    }


def to_json(cis: list[dict], findings: list[Finding], score: float) -> str:
    return json.dumps({"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                       "ci_count": len(cis), "health_score": score, "summary": summarize(findings),
                       "by_class": score_by_class(cis, findings),
                       "findings": [f.to_dict() for f in _sorted(findings)]}, indent=2)


def to_markdown(cis: list[dict], findings: list[Finding], score: float) -> str:
    s = summarize(findings)
    lines = ["# CMDB Data Quality Report", "",
             f"- CIs evaluated: **{len(cis)}**", f"- Health score: **{score} / 100**",
             f"- Findings: **{s['total']}**", "",
             "## Score by class", "", "| Class | CIs | Score |", "|---|---|---|"]
    lines += [f"| {c} | {v['ci_count']} | {v['score']} |" for c, v in score_by_class(cis, findings).items()]
    lines += ["", "## Findings by check", "", "| Check | Count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s["by_check"].items()]
    lines += ["", "## Detail", "", "| Severity | Check | CI | Class | Detail | Remediation |",
              "|---|---|---|---|---|---|"]
    for f in _sorted(findings):
        cells = [f.severity, f.check, f.ci_name or f.sys_id, f.ci_class, f.detail, f.remediation]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def to_csv(findings: list[Finding]) -> str:
    """Remediation worklist; columns map cleanly onto an Import Set or a task load."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["sys_id", "ci_name", "ci_class", "check", "severity", "detail", "remediation"])
    for f in _sorted(findings):
        w.writerow([f.sys_id, f.ci_name, f.ci_class, f.check, f.severity, f.detail, f.remediation])
    return buf.getvalue()


def to_html(cis: list[dict], findings: list[Finding], score: float) -> str:
    e = html.escape
    s = summarize(findings)
    color = "#1a7f37" if score >= 85 else "#9a6700" if score >= 70 else "#cf222e"
    cls_rows = "".join(f"<tr><td>{e(c)}</td><td>{v['ci_count']}</td><td>{v['score']}</td></tr>"
                       for c, v in score_by_class(cis, findings).items())
    rows = "".join(
        f"<tr class='{e(f.severity)}'><td>{e(f.severity)}</td><td>{e(f.check)}</td><td>{e(f.ci_name or f.sys_id)}</td>"
        f"<td>{e(f.ci_class)}</td><td>{e(f.detail)}</td><td>{e(f.remediation)}</td></tr>" for f in _sorted(findings))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CMDB Data Quality Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#1f2328}}h1{{margin:0 0 4px}}
.kpis{{display:flex;gap:16px;margin:16px 0}}.kpi{{border:1px solid #d0d7de;border-radius:8px;padding:12px 16px}}
.kpi b{{display:block;font-size:24px}}table{{border-collapse:collapse;width:100%;margin:8px 0 24px}}
th,td{{border-bottom:1px solid #d0d7de;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f6f8fa}}tr.high td:first-child{{color:#cf222e;font-weight:600}}
tr.medium td:first-child{{color:#9a6700}}</style></head><body>
<h1>CMDB Data Quality Report</h1><div>Generated {stamp}</div>
<div class="kpis"><div class="kpi">Health score<b style="color:{color}">{score}</b></div>
<div class="kpi">CIs evaluated<b>{len(cis)}</b></div><div class="kpi">Findings<b>{s['total']}</b></div>
<div class="kpi">High severity<b>{s['by_severity'].get('high', 0)}</b></div></div>
<h2>Score by class</h2><table><tr><th>Class</th><th>CIs</th><th>Score</th></tr>{cls_rows}</table>
<h2>Findings</h2><table><tr><th>Severity</th><th>Check</th><th>CI</th><th>Class</th><th>Detail</th><th>Remediation</th></tr>
{rows}</table></body></html>
"""
