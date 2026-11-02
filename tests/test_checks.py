from datetime import datetime, timezone
from pathlib import Path

import pytest

from cmdb_dq.__main__ import main
from cmdb_dq.checks import (check_dangling_relationships, check_duplicates, check_orphans,
                            check_required_fields, check_service_without_children, check_stale,
                            health_score, run_checks)
from cmdb_dq.report import to_markdown
from cmdb_dq.source import SourceError, TableApiSource, load_file

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "cmdb_export.json"


@pytest.fixture
def data():
    return load_file(SAMPLE)


def ids(findings, check=None):
    return {f.sys_id for f in findings if check is None or f.check == check}


def test_required_fields(data):
    f = check_required_fields(*data)
    assert {"svc002", "app002", "srv004"} <= ids(f)
    assert "srv001" not in ids(f)


def test_stale_and_never_discovered(data):
    f = check_stale(*data, now=NOW, stale_days=30)
    assert ids(f, "stale") == {"srv002"}
    assert ids(f, "never_discovered") == {"srv004"}
    assert "srv005" not in ids(f)  # retired CI is ignored


def test_duplicates_case_insensitive(data):
    f = check_duplicates(*data)
    assert {"srv002", "srv003"} <= ids(f, "duplicate")


def test_orphans(data):
    f = check_orphans(*data)
    assert "srv004" in ids(f)
    assert "srv005" not in ids(f)  # not operational
    assert "srv001" not in ids(f)


def test_empty_service(data):
    assert ids(check_service_without_children(*data)) == {"svc002"}


def test_dangling_relationship(data):
    f = check_dangling_relationships(*data)
    assert ids(f) == {"rel5"}


def test_health_score_bounds(data):
    cis, rels = data
    findings = run_checks(cis, rels, now=NOW)
    score = health_score(cis, findings)
    assert 0 <= score < 100
    assert health_score(cis, []) == 100.0
    assert health_score([], []) == 100.0


def test_markdown_report(data):
    cis, rels = data
    findings = run_checks(cis, rels, now=NOW)
    md = to_markdown(cis, findings, health_score(cis, findings))
    assert md.startswith("# CMDB Data Quality Report")
    assert "duplicate" in md


def test_load_file_errors(tmp_path):
    with pytest.raises(SourceError):
        load_file(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SourceError):
        load_file(bad)


def test_cli_fail_under(capsys):
    assert main(["--input", str(SAMPLE), "--format", "json"]) == 0
    assert main(["--input", str(SAMPLE), "--fail-under", "99"]) == 2


class FakeResp:
    def __init__(self, status, rows):
        self.status_code, self._rows = status, rows

    def json(self):
        return {"result": self._rows}


class FakeSession:
    def __init__(self, pages, status=200):
        self.pages, self.status, self.calls, self.headers, self.auth = pages, status, [], {}, None

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params)))
        idx = params["sysparm_offset"] // params["sysparm_limit"]
        rows = self.pages.get(url.rsplit("/", 1)[-1], [])[idx * params["sysparm_limit"]:(idx + 1) * params["sysparm_limit"]]
        return FakeResp(self.status, rows)


def test_table_api_pagination():
    cis = [{"sys_id": f"c{i}"} for i in range(5)]
    sess = FakeSession({"cmdb_ci": cis, "cmdb_rel_ci": []})
    src = TableApiSource("https://example.service-now.com", "u", "p", session=sess, page_size=2)
    got_cis, got_rels = src.load()
    assert len(got_cis) == 5 and got_rels == []
    assert len([c for c in sess.calls if c[0].endswith("cmdb_ci")]) == 3


def test_table_api_auth_error_and_https():
    with pytest.raises(SourceError):
        TableApiSource("http://insecure", "u", "p", session=FakeSession({}))
    src = TableApiSource("https://example.service-now.com", "u", "p", session=FakeSession({}, status=401))
    with pytest.raises(SourceError, match="401"):
        src.load()


def test_from_env_missing(monkeypatch):
    for k in ("SN_INSTANCE_URL", "SN_USER", "SN_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SourceError, match="missing"):
        TableApiSource.from_env()
