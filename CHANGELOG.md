# Changelog

## 1.1.0 — 2026-11-03
- Rules in TOML (`--rules`): thresholds, required fields, severity and on/off per check.
- New CSDM checks: `service_without_business_app`, `retired_in_use`.
- Remediation guidance on every finding; score by CMDB class.
- New outputs: self-contained HTML report and remediation CSV worklist; `--output`.
- Score history with delta (`--history`).
- Table API client: retry with backoff on 429/5xx (honours Retry-After), OAuth bearer token, clearer 401/403 errors.
- Local mock Table API (`cmdb-dq-mock`) and docker-compose live-mode demo.
- Packaging (`pip install .`, `cmdb-dq` command), Dockerfile, Makefile, ruff, coverage gate, scheduled report workflow.

## 1.0.0 — 2026-11-02
- First release: completeness, staleness, duplicate, orphan, empty-service and dangling-relationship checks; Markdown/JSON output; Table API reader.
