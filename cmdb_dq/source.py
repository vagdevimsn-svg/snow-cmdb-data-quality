"""Data sources: a JSON export on disk, or a live instance through the ServiceNow Table API.

Credentials are read from environment variables only and are never logged. The client is
read-only (GET), pages through results, and retries 429/5xx responses with backoff,
honouring Retry-After when the instance sends it (ServiceNow rate-limit rules do).
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

CI_TABLE = "cmdb_ci"
REL_TABLE = "cmdb_rel_ci"
CI_FIELDS = ("sys_id,name,sys_class_name,serial_number,ip_address,os,support_group,owned_by,"
             "it_application_owner,install_status,last_discovered,busines_criticality")
RETRY_STATUS = {429, 500, 502, 503, 504}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


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
    """Minimal paginated, read-only reader for the ServiceNow Table API."""

    def __init__(self, instance_url: str, user: str = "", password: str = "", token: str = "",
                 session=None, page_size: int = 500, timeout: int = 30, max_retries: int = 3,
                 backoff: float = 1.0, sleep=time.sleep, allow_insecure_http: bool = False):
        parsed = urlparse(instance_url)
        local_http = parsed.scheme == "http" and (parsed.hostname in LOCAL_HOSTS or allow_insecure_http)
        if parsed.scheme != "https" and not local_http:
            raise SourceError("instance URL must use https (plain http is allowed only for a local mock)")
        if parsed.scheme == "http":
            log.warning("using plain http to %s - only acceptable for the local mock server", parsed.hostname)
        if not token and not (user and password):
            raise SourceError("provide SN_TOKEN (OAuth bearer) or SN_USER and SN_PASSWORD")
        self.base = instance_url.rstrip("/")
        self.page_size, self.timeout = page_size, timeout
        self.max_retries, self.backoff, self._sleep = max_retries, backoff, sleep
        if session is None:
            import requests  # imported lazily so file mode has no dependency
            session = requests.Session()
        self.session = session
        self.session.headers.update({"Accept": "application/json"})
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.auth = (user, password)

    @classmethod
    def from_env(cls, **kw) -> TableApiSource:
        url = os.environ.get("SN_INSTANCE_URL", "")
        if not url:
            raise SourceError("missing environment variable: SN_INSTANCE_URL")
        kw.setdefault("allow_insecure_http", os.environ.get("SN_ALLOW_INSECURE_HTTP", "").lower() == "true")
        return cls(url, os.environ.get("SN_USER", ""), os.environ.get("SN_PASSWORD", ""),
                   os.environ.get("SN_TOKEN", ""), **kw)

    def _get(self, url: str, params: dict):
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except OSError as exc:  # requests' ConnectionError/Timeout subclass OSError
                if attempt == self.max_retries:
                    raise SourceError(f"cannot reach {self.base}: {exc.__class__.__name__}") from exc
                self._sleep(self.backoff * 2 ** attempt)
                continue
            if resp.status_code not in RETRY_STATUS or attempt == self.max_retries:
                return resp
            retry_after = getattr(resp, "headers", {}).get("Retry-After")
            wait = float(retry_after) if retry_after and str(retry_after).isdigit() else self.backoff * 2 ** attempt
            log.warning("HTTP %s from %s; retry %d/%d in %.1fs", resp.status_code, url, attempt + 1,
                        self.max_retries, wait)
            self._sleep(wait)
        return resp  # pragma: no cover

    def _get_all(self, table: str, fields: str, query: str = "") -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while True:
            params = {"sysparm_fields": fields, "sysparm_limit": self.page_size, "sysparm_offset": offset,
                      "sysparm_exclude_reference_link": "true", "sysparm_display_value": "false"}
            if query:
                params["sysparm_query"] = query
            resp = self._get(f"{self.base}/api/now/table/{table}", params)
            if resp.status_code == 401:
                raise SourceError("authentication failed (401) - check credentials")
            if resp.status_code == 403:
                raise SourceError(f"{table}: access denied (403) - the user needs read access (e.g. cmdb_read)")
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
