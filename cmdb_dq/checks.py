"""CMDB data-quality checks modelled on the CSDM health dimensions:
completeness, correctness (staleness, duplicates) and compliance (relationships, ownership).

Every check takes the full dataset and returns a list of Finding objects, so checks stay
independent and easy to unit test. Thresholds and required fields come from a Rules object
(see rules.py), which defaults to rules/default.toml.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from .rules import Rules, default_rules

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
OPERATIONAL = "1"  # install_status = Installed
RETIRED = "7"      # install_status = Retired


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    sys_id: str
    ci_name: str
    ci_class: str
    detail: str
    remediation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _f(check: str, ci: dict, detail: str, rules: Rules, remediation: str) -> Finding:
    return Finding(check, rules.severity(check), ci.get("sys_id", ""), ci.get("name", ""),
                   ci.get("sys_class_name", ""), detail, remediation)


# --- completeness ---------------------------------------------------------------------------
def check_required_fields(cis: list[dict], rels: list[dict], rules: Rules | None = None, **_) -> list[Finding]:
    rules = rules or default_rules()
    out = []
    for ci in cis:
        for field in rules.required_fields.get(ci.get("sys_class_name", ""), []):
            if not str(ci.get(field) or "").strip():
                out.append(_f("missing_field", ci, f"'{field}' is empty", rules,
                              f"Populate {field} (owner/support data drives assignment and impact)"))
    return out


# --- correctness ----------------------------------------------------------------------------
def check_stale(cis: list[dict], rels: list[dict], now: datetime, stale_days: int | None = None,
                rules: Rules | None = None, **_) -> list[Finding]:
    """Operational discoverable CIs that Discovery has not seen recently."""
    rules = rules or default_rules()
    days = stale_days if stale_days is not None else rules.stale_days
    cutoff = now - timedelta(days=days)
    out = []
    for ci in cis:
        if ci.get("sys_class_name") not in rules.discoverable_classes or ci.get("install_status") != OPERATIONAL:
            continue
        seen = _parse_ts(ci.get("last_discovered"))
        if seen is None:
            out.append(_f("never_discovered", ci, "operational CI has no last_discovered date", rules,
                          "Add the CI's IP range to a Discovery schedule or confirm it is manually managed"))
        elif seen < cutoff:
            out.append(_f("stale", ci, f"last discovered {(now - seen).days} days ago (> {days})", rules,
                          "Check Discovery schedule, MID Server reachability and credentials; "
                          "retire if decommissioned"))
    return out


def check_duplicates(cis: list[dict], rels: list[dict], rules: Rules | None = None, **_) -> list[Finding]:
    """Same serial number (servers) or same name within a class -> likely IRE/reconciliation gap."""
    rules = rules or default_rules()
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for ci in cis:
        cls = ci.get("sys_class_name", "")
        serial = (ci.get("serial_number") or "").strip().upper()
        if cls == "cmdb_ci_server" and serial:
            by_key[("serial", serial)].append(ci)
        name = (ci.get("name") or "").strip().lower()
        if name:
            by_key[("name", cls, name)].append(ci)
    out, seen_groups = [], set()
    for key, group in by_key.items():
        ids = tuple(sorted(c["sys_id"] for c in group))
        if len(group) < 2 or ids in seen_groups:
            continue
        seen_groups.add(ids)
        for ci in group:
            others = ", ".join(c["sys_id"] for c in group if c is not ci)
            out.append(_f("duplicate", ci, f"duplicate on {key[0]} with: {others}", rules,
                          "Review IRE identification rules; merge or retire the duplicate CI"))
    return out


def check_dangling_relationships(cis: list[dict], rels: list[dict], rules: Rules | None = None, **_) -> list[Finding]:
    rules = rules or default_rules()
    ids = {c["sys_id"] for c in cis}
    out = []
    for r in rels:
        for end in ("parent", "child"):
            if r.get(end) not in ids:
                out.append(Finding("dangling_relationship", rules.severity("dangling_relationship"),
                                   r.get("sys_id", ""), "", "cmdb_rel_ci", f"{end} {r.get(end)} does not exist",
                                   "Delete the relationship or restore the missing CI"))
    return out


# --- compliance (CSDM) ----------------------------------------------------------------------
def check_orphans(cis: list[dict], rels: list[dict], rules: Rules | None = None, **_) -> list[Finding]:
    """Operational CIs with no relationship cannot feed service impact analysis."""
    rules = rules or default_rules()
    related = {r.get("parent") for r in rels} | {r.get("child") for r in rels}
    return [_f("orphan", ci, "no cmdb_rel_ci relationships", rules,
               "Map the CI with Service Mapping or add a Runs on / Depends on relationship")
            for ci in cis if ci.get("install_status") == OPERATIONAL and ci["sys_id"] not in related
            and ci.get("sys_class_name") not in rules.orphan_exempt_classes]


def check_service_without_children(cis: list[dict], rels: list[dict], rules: Rules | None = None, **_) -> list[Finding]:
    """An application service should depend on at least one application or infrastructure CI."""
    rules = rules or default_rules()
    parents = {r.get("parent") for r in rels}
    return [_f("empty_service", ci, "application service has no downstream dependencies mapped", rules,
               "Run Service Mapping or build the service from tags/dynamic CI groups")
            for ci in cis if ci.get("sys_class_name") == "cmdb_ci_service_auto" and ci["sys_id"] not in parents]


def check_service_without_business_app(cis: list[dict], rels: list[dict], rules: Rules | None = None,
                                       **_) -> list[Finding]:
    """CSDM 'Crawl/Walk': each application service should be consumed by a business application."""
    rules = rules or default_rules()
    by_id = {c["sys_id"]: c for c in cis}
    consumed = {r.get("child") for r in rels
                if by_id.get(r.get("parent"), {}).get("sys_class_name") == "cmdb_ci_business_app"}
    return [_f("service_without_business_app", ci, "no business application consumes this service", rules,
               "Link the service to its cmdb_ci_business_app (Consumes::Consumed by)")
            for ci in cis if ci.get("sys_class_name") == "cmdb_ci_service_auto" and ci["sys_id"] not in consumed]


def check_retired_in_use(cis: list[dict], rels: list[dict], rules: Rules | None = None, **_) -> list[Finding]:
    """A retired CI that an operational CI still depends on makes impact analysis wrong."""
    rules = rules or default_rules()
    by_id = {c["sys_id"]: c for c in cis}
    out = []
    for r in rels:
        parent, child = by_id.get(r.get("parent")), by_id.get(r.get("child"))
        if parent and child and child.get("install_status") == RETIRED and parent.get("install_status") == OPERATIONAL:
            out.append(_f("retired_in_use", child, f"retired but still a dependency of {parent.get('name')}", rules,
                          "Remove the relationship or correct install_status"))
    return out


ALL_CHECKS: dict[str, Callable[..., list[Finding]]] = {
    "missing_field": check_required_fields,
    "stale": check_stale,
    "duplicate": check_duplicates,
    "orphan": check_orphans,
    "empty_service": check_service_without_children,
    "service_without_business_app": check_service_without_business_app,
    "retired_in_use": check_retired_in_use,
    "dangling_relationship": check_dangling_relationships,
}


def run_checks(cis: list[dict], rels: list[dict], now: datetime | None = None, stale_days: int | None = None,
               rules: Rules | None = None,
               checks: Iterable[Callable[..., list[Finding]]] | None = None) -> list[Finding]:
    rules = rules or default_rules()
    now = now or datetime.now(UTC)
    selected = checks if checks is not None else [fn for name, fn in ALL_CHECKS.items() if rules.enabled(name)]
    findings: list[Finding] = []
    for check in selected:
        findings.extend(check(cis, rels, now=now, stale_days=stale_days, rules=rules))
    return findings


def health_score(cis: list[dict], findings: list[Finding]) -> float:
    """0-100. Weighted penalty per CI, capped so one bad CI cannot zero the score."""
    if not cis:
        return 100.0
    ids = {c["sys_id"] for c in cis}
    penalty: dict[str, int] = defaultdict(int)
    for f in findings:
        if f.sys_id in ids:
            penalty[f.sys_id] += SEVERITY_WEIGHT.get(f.severity, 1)
    cap = 6
    total = sum(min(p, cap) for p in penalty.values())
    return round(100.0 * (1 - total / (cap * len(cis))), 1)


def score_by_class(cis: list[dict], findings: list[Finding]) -> dict[str, dict]:
    """Health score and CI count per CMDB class, worst first."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for ci in cis:
        groups[ci.get("sys_class_name", "")].append(ci)
    out = {}
    for cls, members in groups.items():
        ids = {c["sys_id"] for c in members}
        out[cls] = {"ci_count": len(members),
                    "score": health_score(members, [f for f in findings if f.sys_id in ids])}
    return dict(sorted(out.items(), key=lambda kv: kv[1]["score"]))
