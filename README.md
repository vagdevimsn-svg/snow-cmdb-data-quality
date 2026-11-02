# snow-cmdb-data-quality

A small command-line tool that scores the health of a ServiceNow CMDB and lists the CIs that weaken Incident and Change impact analysis: missing ownership, stale Discovery data, duplicates, orphan CIs and application services with nothing mapped underneath them.

> **Portfolio project.** Independently written, using synthetic data. It is not code from any employer or client, and it contains no client data.

## Why

Event Management, Service Mapping and Change risk all depend on the CMDB. When servers stop being discovered, duplicates slip past reconciliation, or an application service has no dependencies, alerts attach to the wrong CI and change impact is guessed instead of calculated. This tool gives a repeatable, scriptable check you can run before an audit, after a Discovery schedule change, or in a pipeline.

## What it checks

| Check | Severity | CSDM dimension | Rule |
|---|---|---|---|
| `missing_field` | medium | Completeness | Class-specific required fields (owner, support group, serial, IP, OS, criticality) |
| `never_discovered` | high | Correctness | Operational server/DB with no `last_discovered` |
| `stale` | medium | Correctness | Operational server/DB not discovered within `--stale-days` |
| `duplicate` | high | Correctness | Same serial number (case-insensitive) or same name within a class |
| `orphan` | medium | Compliance | Operational CI with no `cmdb_rel_ci` relationship |
| `empty_service` | high | Compliance | Application service (`cmdb_ci_service_auto`) with no downstream CI |
| `dangling_relationship` | low | Correctness | Relationship pointing to a CI that does not exist |

The health score is 0-100: each CI loses weighted points per finding (high 3, medium 2, low 1), capped at 6 per CI so one broken record cannot hide the rest.

## Architecture

```
            +--------------------+        +-------------+       +---------------+
JSON export |  source.load_file  |        |             |       | report (md /  |
----------->|                    |--CIs-->|  checks.py  |------>| json), score, |
            |  TableApiSource    |  rels  | (pure funcs)|       | exit code     |
Table API ->|  (paginated, RO)   |        |             |       |               |
            +--------------------+        +-------------+       +---------------+
```

Each check is a pure function `(cis, rels, **opts) -> list[Finding]`, so new rules are easy to add and unit test.

## Quick start

```bash
git clone https://github.com/vagdevimsn-svg/snow-cmdb-data-quality.git
cd snow-cmdb-data-quality
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

python sample_data/generate.py            # optional: regenerate synthetic data
python -m cmdb_dq --input sample_data/cmdb_export.json
python -m cmdb_dq --input sample_data/cmdb_export.json --format json --fail-under 80
```

Sample output: [docs/sample_report.md](docs/sample_report.md)

### Against a personal developer instance

```bash
cp .env.example .env    # fill in a PDI URL and a read-only user
set -a; source .env; set +a
python -m cmdb_dq --live --query "install_status=1"
```

Live mode only issues `GET` requests to `/api/now/table/cmdb_ci` and `/api/now/table/cmdb_rel_ci`, pages through results, and requires `https`.

## Tests

```bash
python -m pytest -q
```

Tests cover each rule, scoring, report output, CLI exit codes, Table API pagination and error handling (using a fake HTTP session, no network).

## Security notes

- Credentials come from environment variables only; `.env` is git-ignored and never logged.
- Use a dedicated integration account with read-only CMDB roles.
- Sample data is fictitious (`SYN-` serials, RFC 1918 addresses, made-up names).

## Limitations and next steps

- Name-based duplicate detection is simple; production reconciliation should rely on IRE identification rules.
- Reads base `cmdb_ci` fields only; class-specific attributes would need per-class queries.
- Next: CSDM layer checks (business application → application service → technical service offering), trend history, and a scheduled GitHub Action that posts the score.

## License

MIT
