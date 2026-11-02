"""CMDB data-quality checks loosely modelled on CSDM health dimensions:
completeness, correctness (staleness, duplicates) and compliance (relationships, ownership).

Every check takes the full dataset and returns a list of Finding objects so checks
stay independent and easy to unit test.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Fields a CI of each class must carry to be useful for Incident/Change impact analysis.
REQUIRED_FIELDS = {
    "cmdb_ci_server": ["name", "serial_number", "ip_address", "os", "support_group", "install_status"],
    "cmdb_ci_appl": ["name", "owned_by", "support_group", "install_status"],
    "cmdb_ci_service_auto": ["name", "owned_by", "support_group", "busines_criticality"],
    "cmdb_ci_db_instance": ["name", "support_group", "install_status"],
}

OPERATIONAL = "1"  # install_status = Installed


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    sys_id: str
    ci_name: str
    ci_class: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def check_required_fields(cis: list[dict], rels: list[dict], **_) -> list[Finding]:
    out = []
    for ci in cis:
        for field in REQUIRED_FIELDS.get(ci.get("sys_class_name", ""), []):
            if not str(ci.get(field) or "").strip():
                out.append(Finding("missing_field", "medium", ci["sys_id"], ci.get("name", ""),
                                   ci.get("sys_class_name", ""), f"'{field}' is empty"))
    return out


def check_stale(cis: list[dict], rels: list[dict], now: datetime, stale_days: int = 30, **_) -> list[Finding]:
    """Operational servers/DBs that Discovery has not seen recently."""
    out = []
    cutoff = now - timedelta(days=stale_days)
    for ci in cis:
        if ci.get("sys_class_name") not in ("cmdb_ci_server", "cmdb_ci_db_instance"):
            continue
        if ci.get("install_status") != OPERATIONAL:
            continue
        seen = _parse_ts(ci.get("last_discovered"))
        if seen is None:
            out.append(Finding("never_discovered", "high", ci["sys_id"], ci.get("name", ""),
                               ci["sys_class_name"], "operational CI has no last_discovered date"))
        elif seen < cutoff:
            age = (now - seen).days
            out.append(Finding("stale", "medium", ci["sys_id"], ci.get("name", ""),
                               ci["sys_class_name"], f"last discovered {age} days ago (> {stale_days})"))
    return out


def check_duplicates(cis: list[dict], rels: list[dict], **_) -> list[Finding]:
    """Same serial number (servers) or same name within a class -> likely IRE/reconciliation gap."""
    out = []
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for ci in cis:
        cls = ci.get("sys_class_name", "")
        serial = (ci.get("serial_number") or "").strip().upper()
        if cls == "cmdb_ci_server" and serial:
            by_key[("serial", serial)].append(ci)
        name = (ci.get("name") or "").strip().lower()
        if name:
            by_key[("name", cls, name)].append(ci)
    seen_pairs = set()
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        ids = tuple(sorted(c["sys_id"] for c in group))
        if ids in seen_pairs:
            continue
        seen_pairs.add(ids)
        for ci in group:
            out.append(Finding("duplicate", "high", ci["sys_id"], ci.get("name", ""), ci.get("sys_class_name", ""),
                               f"duplicate on {key[0]} with {len(group) - 1} other CI(s): "
                               + ", ".join(c["sys_id"] for c in group if c is not ci)))
    return out


def check_orphans(cis: list[dict], rels: list[dict], **_) -> list[Finding]:
    """Operational CIs with no relationship at all cannot feed service impact analysis."""
    related = set()
    for r in rels:
        related.add(r.get("parent"))
        related.add(r.get("child"))
    out = []
    for ci in cis:
        if ci.get("install_status") == OPERATIONAL and ci["sys_id"] not in related:
            out.append(Finding("orphan", "medium", ci["sys_id"], ci.get("name", ""), ci.get("sys_class_name", ""),
                               "no cmdb_rel_ci relationships"))
    return out


def check_service_without_children(cis: list[dict], rels: list[dict], **_) -> list[Finding]:
    """CSDM: an application service should depend on at least one application or infrastructure CI."""
    parents = {r.get("parent") for r in rels}
    out = []
    for ci in cis:
        if ci.get("sys_class_name") == "cmdb_ci_service_auto" and ci["sys_id"] not in parents:
            out.append(Finding("empty_service", "high", ci["sys_id"], ci.get("name", ""), ci["sys_class_name"],
                               "application service has no downstream dependencies mapped"))
    return out


def check_dangling_relationships(cis: list[dict], rels: list[dict], **_) -> list[Finding]:
    ids = {c["sys_id"] for c in cis}
    out = []
    for r in rels:
        for end in ("parent", "child"):
            if r.get(end) not in ids:
                out.append(Finding("dangling_relationship", "low", r.get("sys_id", ""), "", "cmdb_rel_ci",
                                   f"{end} {r.get(end)} does not exist"))
    return out


ALL_CHECKS: list[Callable[..., list[Finding]]] = [
    check_required_fields,
    check_stale,
    check_duplicates,
    check_orphans,
    check_service_without_children,
    check_dangling_relationships,
]


def run_checks(cis: list[dict], rels: list[dict], now: datetime | None = None, stale_days: int = 30,
               checks: Iterable[Callable[..., list[Finding]]] = ALL_CHECKS) -> list[Finding]:
    now = now or datetime.now(timezone.utc)
    findings: list[Finding] = []
    for check in checks:
        findings.extend(check(cis, rels, now=now, stale_days=stale_days))
    return findings


def health_score(cis: list[dict], findings: list[Finding]) -> float:
    """0-100. Weighted penalty per CI, capped so one bad CI cannot zero the score."""
    if not cis:
        return 100.0
    penalty_by_ci: dict[str, int] = defaultdict(int)
    for f in findings:
        penalty_by_ci[f.sys_id] += SEVERITY_WEIGHT.get(f.severity, 1)
    max_per_ci = 6
    total = sum(min(p, max_per_ci) for sid, p in penalty_by_ci.items() if any(c["sys_id"] == sid for c in cis))
    return round(100.0 * (1 - total / (max_per_ci * len(cis))), 1)
