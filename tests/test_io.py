"""Reports, CLI, history, Table API client and the mock server end to end."""
import csv
import io
import json
import socket
from pathlib import Path

import pytest

from cmdb_dq.__main__ import main
from cmdb_dq.checks import health_score, run_checks
from cmdb_dq.mock_server import serve
from cmdb_dq.report import to_csv, to_html, to_markdown
from cmdb_dq.source import SourceError, TableApiSource, load_file

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "cmdb_export.json"


@pytest.fixture
def result():
    cis, rels = load_file(SAMPLE)
    findings = run_checks(cis, rels)
    return cis, findings, health_score(cis, findings)


def test_markdown_report(result):
    md = to_markdown(*result)
    assert md.startswith("# CMDB Data Quality Report")
    assert "Score by class" in md and "Remediation" in md


def test_html_report_escapes_and_is_self_contained(result):
    cis, findings, score = result
    cis = cis + [{"sys_id": "x1", "name": "<script>alert(1)</script>", "sys_class_name": "cmdb_ci_appl",
                  "install_status": "1"}]
    page = to_html(cis, run_checks(cis, []), score)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert "http" not in page.split("<body>")[0].replace("http-equiv", "")  # no external assets


def test_csv_worklist(result):
    _, findings, _ = result
    rows = list(csv.DictReader(io.StringIO(to_csv(findings))))
    assert len(rows) == len(findings)
    assert rows[0]["severity"] == "high"
    assert set(rows[0]) == {"sys_id", "ci_name", "ci_class", "check", "severity", "detail", "remediation"}


def test_cli_formats_output_and_fail_under(tmp_path, capsys):
    out = tmp_path / "r.html"
    assert main(["--input", str(SAMPLE), "--format", "html", "--output", str(out)]) == 0
    assert out.read_text().startswith("<!doctype html>")
    assert main(["--input", str(SAMPLE), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["ci_count"] == 11
    assert main(["--input", str(SAMPLE), "--fail-under", "99"]) == 2
    assert main(["--input", str(tmp_path / "missing.json")]) == 1
    assert main(["--input", str(SAMPLE), "--rules", str(tmp_path / "nope.toml")]) == 1


def test_history_appends_with_delta(tmp_path):
    hist = tmp_path / "history.json"
    main(["--input", str(SAMPLE), "--format", "json", "--output", str(tmp_path / "a.json"), "--history", str(hist)])
    main(["--input", str(SAMPLE), "--format", "json", "--output", str(tmp_path / "b.json"), "--history", str(hist)])
    entries = json.loads(hist.read_text())
    assert len(entries) == 2 and entries[0]["delta"] is None and entries[1]["delta"] == 0.0


class FakeResp:
    def __init__(self, status, rows=(), headers=None):
        self.status_code, self._rows, self.headers = status, list(rows), headers or {}

    def json(self):
        return {"result": self._rows}


class FakeSession:
    def __init__(self, pages, statuses=None):
        self.pages, self.statuses, self.calls, self.headers, self.auth = pages, list(statuses or []), [], {}, None

    def get(self, url, params, timeout):
        self.calls.append((url, dict(params)))
        if self.statuses:
            return FakeResp(self.statuses.pop(0), headers={"Retry-After": "0"})
        limit, off = params["sysparm_limit"], params["sysparm_offset"]
        return FakeResp(200, self.pages.get(url.rsplit("/", 1)[-1], [])[off:off + limit])


def test_table_api_pagination():
    sess = FakeSession({"cmdb_ci": [{"sys_id": f"c{i}"} for i in range(5)], "cmdb_rel_ci": []})
    cis, rels = TableApiSource("https://example.service-now.com", "u", "p", session=sess, page_size=2).load()
    assert len(cis) == 5 and rels == []
    assert len([c for c in sess.calls if c[0].endswith("cmdb_ci")]) == 3


def test_table_api_retries_then_succeeds():
    waits = []
    sess = FakeSession({"cmdb_ci": [{"sys_id": "a"}], "cmdb_rel_ci": []}, statuses=[429, 503])
    src = TableApiSource("https://example.service-now.com", "u", "p", session=sess, sleep=waits.append)
    cis, _ = src.load()
    assert cis == [{"sys_id": "a"}] and len(waits) == 2


def test_table_api_gives_up_after_max_retries():
    sess = FakeSession({}, statuses=[503] * 5)
    src = TableApiSource("https://example.service-now.com", "u", "p", session=sess, max_retries=2, sleep=lambda s: None)
    with pytest.raises(SourceError, match="503"):
        src.load()


def test_bearer_token_auth():
    sess = FakeSession({"cmdb_ci": [], "cmdb_rel_ci": []})
    TableApiSource("https://example.service-now.com", token="abc", session=sess)
    assert sess.headers["Authorization"] == "Bearer abc" and sess.auth is None


@pytest.mark.parametrize("status,msg", [(401, "401"), (403, "403")])
def test_auth_errors(status, msg):
    sess = FakeSession({}, statuses=[status])
    with pytest.raises(SourceError, match=msg):
        TableApiSource("https://example.service-now.com", "u", "p", session=sess).load()


def test_url_and_credential_validation(monkeypatch):
    with pytest.raises(SourceError, match="https"):
        TableApiSource("http://example.com", "u", "p", session=FakeSession({}))
    with pytest.raises(SourceError, match="SN_TOKEN"):
        TableApiSource("https://example.service-now.com", session=FakeSession({}))
    TableApiSource("http://mock:8080", "u", "p", session=FakeSession({}), allow_insecure_http=True)
    monkeypatch.delenv("SN_INSTANCE_URL", raising=False)
    with pytest.raises(SourceError, match="SN_INSTANCE_URL"):
        TableApiSource.from_env()


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_live_mode_against_mock_server(monkeypatch, capsys):
    pytest.importorskip("requests")
    port = _free_port()
    server = serve(SAMPLE, port, background=True)
    try:
        monkeypatch.setenv("SN_INSTANCE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setenv("SN_USER", "demo")
        monkeypatch.setenv("SN_PASSWORD", "demo")
        assert main(["--live", "--format", "json"]) == 0
        assert json.loads(capsys.readouterr().out)["ci_count"] == 11
        monkeypatch.setenv("SN_PASSWORD", "wrong")
        assert main(["--live"]) == 1
    finally:
        server.shutdown()


def test_mock_server_errors_and_field_selection():
    requests = pytest.importorskip("requests")
    port = _free_port()
    server = serve(SAMPLE, port, background=True)
    base = f"http://127.0.0.1:{port}"
    try:
        assert requests.get(f"{base}/api/now/table/cmdb_ci", timeout=5).status_code == 401
        auth = ("demo", "demo")
        assert requests.get(f"{base}/other", auth=auth, timeout=5).status_code == 404
        assert requests.get(f"{base}/api/now/table/incident", auth=auth, timeout=5).status_code == 400
        rows = requests.get(f"{base}/api/now/table/cmdb_ci", auth=auth, timeout=5,
                            params={"sysparm_fields": "sys_id,name", "sysparm_limit": 2}).json()["result"]
        assert len(rows) == 2 and set(rows[0]) == {"sys_id", "name"}
    finally:
        server.shutdown()


def test_unreachable_instance_raises_source_error():
    pytest.importorskip("requests")
    src = TableApiSource(f"http://127.0.0.1:{_free_port()}", "u", "p", max_retries=1, sleep=lambda s: None)
    with pytest.raises(SourceError, match="cannot reach"):
        src.load()
