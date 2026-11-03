from datetime import UTC, datetime
from pathlib import Path

import pytest

from cmdb_dq.checks import (
    check_dangling_relationships,
    check_duplicates,
    check_orphans,
    check_required_fields,
    check_retired_in_use,
    check_service_without_business_app,
    check_service_without_children,
    check_stale,
    health_score,
    run_checks,
    score_by_class,
)
from cmdb_dq.rules import RulesError, load_rules
from cmdb_dq.source import SourceError, load_file

NOW = datetime(2026, 11, 1, tzinfo=UTC)
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
    assert all(x.remediation for x in f)


def test_stale_and_never_discovered(data):
    f = check_stale(*data, now=NOW, stale_days=30)
    assert ids(f, "stale") == {"srv002"}
    assert ids(f, "never_discovered") == {"srv004"}
    assert "srv005" not in ids(f)  # retired CI is ignored


def test_stale_days_from_rules(data, tmp_path):
    rules_file = tmp_path / "r.toml"
    rules_file.write_text('stale_days = 200\ndiscoverable_classes = ["cmdb_ci_server"]\n')
    f = check_stale(*data, now=NOW, rules=load_rules(rules_file))
    assert ids(f, "stale") == set()


def test_duplicates_case_insensitive(data):
    assert {"srv002", "srv003"} <= ids(check_duplicates(*data), "duplicate")


def test_orphans_respect_exempt_classes(data):
    f = check_orphans(*data)
    assert "srv004" in ids(f)
    assert "srv005" not in ids(f)  # not operational
    assert "bapp01" not in ids(f)


def test_empty_service(data):
    assert ids(check_service_without_children(*data)) == {"svc002"}


def test_service_without_business_app(data):
    assert ids(check_service_without_business_app(*data)) == {"svc002"}


def test_retired_in_use(data):
    assert ids(check_retired_in_use(*data)) == {"srv005"}


def test_dangling_relationship(data):
    assert ids(check_dangling_relationships(*data)) == {"rel5"}


def test_disabled_check_is_skipped(data, tmp_path):
    rules_file = tmp_path / "r.toml"
    rules_file.write_text("[checks]\nduplicate = { enabled = false }\n")
    found = run_checks(*data, now=NOW, rules=load_rules(rules_file))
    assert not ids(found, "duplicate")


def test_severity_from_rules(data, tmp_path):
    rules_file = tmp_path / "r.toml"
    rules_file.write_text('[checks]\norphan = { severity = "low" }\n')
    found = run_checks(*data, now=NOW, rules=load_rules(rules_file))
    assert {f.severity for f in found if f.check == "orphan"} == {"low"}


@pytest.mark.parametrize("content", ["stale_days = -1", "[checks]\nx = { severity = \"urgent\" }", "not toml ="])
def test_invalid_rules(tmp_path, content):
    p = tmp_path / "bad.toml"
    p.write_text(content)
    with pytest.raises(RulesError):
        load_rules(p)


def test_missing_rules_file(tmp_path):
    with pytest.raises(RulesError):
        load_rules(tmp_path / "missing.toml")


def test_health_score_bounds_and_by_class(data):
    cis, rels = data
    findings = run_checks(cis, rels, now=NOW)
    score = health_score(cis, findings)
    assert 0 <= score < 100
    assert health_score(cis, []) == 100.0
    assert health_score([], []) == 100.0
    by_class = score_by_class(cis, findings)
    assert list(by_class)[0] == "cmdb_ci_server"  # worst class first
    assert by_class["cmdb_ci_business_app"]["score"] == 100.0


def test_load_file_errors(tmp_path):
    with pytest.raises(SourceError):
        load_file(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(SourceError):
        load_file(bad)
