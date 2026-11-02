"""Data sources: a JSON export on disk, or a live instance through the ServiceNow Table API.

Credentials are read from environment variables only and are never logged.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

CI_TABLE = "cmdb_ci"
REL_TABLE = "cmdb_rel_ci"
CI_FIELDS = ("sys_id,name,sys_class_name,serial_number,ip_address,os,support_group,owned_by,"
             "install_status,last_discovered,busines_criticality")


class SourceError(RuntimeError):
    pass


def load_file(path: str | Path) -> tuple[list[dict], list[dict]]:
    p = Path(path)
    if not p.exists():
        raise SourceError(f"input file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"{p} is not valid JSON: {exc}") from exc
    cis, rels = data.get("cmdb_ci", []), data.get("cmdb_rel_ci", [])
    if not isinstance(cis, list) or not isinstance(rels, list):
        raise SourceError("expected 'cmdb_ci' and 'cmdb_rel_ci' arrays")
    log.info("loaded %d CIs and %d relationships from %s", len(cis), len(rels), p)
    return cis, rels


class TableApiSource:
    """Minimal paginated reader for the ServiceNow Table API (read-only)."""

    def __init__(self, instance_url: str, user: str, password: str, session=None, page_size: int = 500,
                 timeout: int = 30):
        if not instance_url.startswith("https://"):
            raise SourceError("instance URL must use https")
        self.base = instance_url.rstrip("/")
        self.page_size = page_size
        self.timeout = timeout
        if session is None:
            import requests  # imported lazily so file mode has no dependency
            session = requests.Session()
        self.session = session
        self.session.auth = (user, password)
        self.session.headers.update({"Accept": "application/json"})

    @classmethod
    def from_env(cls, **kw) -> "TableApiSource":
        missing = [k for k in ("SN_INSTANCE_URL", "SN_USER", "SN_PASSWORD") if not os.environ.get(k)]
        if missing:
            raise SourceError("missing environment variables: " + ", ".join(missing))
        return cls(os.environ["SN_INSTANCE_URL"], os.environ["SN_USER"], os.environ["SN_PASSWORD"], **kw)

    def _get_all(self, table: str, fields: str, query: str = "") -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            params = {"sysparm_fields": fields, "sysparm_limit": self.page_size, "sysparm_offset": offset,
                      "sysparm_exclude_reference_link": "true", "sysparm_display_value": "false"}
            if query:
                params["sysparm_query"] = query
            resp = self.session.get(f"{self.base}/api/now/table/{table}", params=params, timeout=self.timeout)
            if resp.status_code == 401:
                raise SourceError("authentication failed (401) - check SN_USER / SN_PASSWORD")
            if resp.status_code >= 400:
                raise SourceError(f"{table}: HTTP {resp.status_code}")
            batch = resp.json().get("result", [])
            rows.extend(batch)
            log.debug("%s: fetched %d rows (offset %d)", table, len(batch), offset)
            if len(batch) < self.page_size:
                return rows
            offset += self.page_size

    def load(self, ci_query: str = "") -> tuple[list[dict], list[dict]]:
        cis = self._get_all(CI_TABLE, CI_FIELDS, ci_query)
        rels = self._get_all(REL_TABLE, "sys_id,parent,child,type")
        log.info("fetched %d CIs and %d relationships from %s", len(cis), len(rels), self.base)
        return cis, rels
