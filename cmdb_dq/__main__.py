"""CLI: cmdb-dq --input sample_data/cmdb_export.json --format html --output report.html"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__
from .checks import health_score, run_checks
from .history import append as append_history
from .report import to_csv, to_html, to_json, to_markdown
from .rules import RulesError, load_rules
from .source import SourceError, TableApiSource, load_file

WRITERS = {"md": to_markdown, "json": to_json, "html": to_html}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cmdb-dq", description="CMDB data-quality checks (CSDM-style)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="JSON export with cmdb_ci and cmdb_rel_ci arrays")
    src.add_argument("--live", action="store_true", help="read from an instance using SN_* environment variables")
    ap.add_argument("--query", default="", help="encoded query to scope CIs in live mode, e.g. install_status=1")
    ap.add_argument("--rules", help="TOML rules file (default: built-in rules/default.toml)")
    ap.add_argument("--stale-days", type=int, default=None, help="override stale_days from the rules file")
    ap.add_argument("--format", choices=tuple(WRITERS) + ("csv",), default="md")
    ap.add_argument("--output", help="write the report to this file instead of stdout")
    ap.add_argument("--history", help="append the score to this JSON history file")
    ap.add_argument("--fail-under", type=float, default=None, help="exit 2 if health score is below this value")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    try:
        rules = load_rules(args.rules)
        cis, rels = load_file(args.input) if args.input else TableApiSource.from_env().load(args.query)
    except (SourceError, RulesError) as exc:
        logging.error("%s", exc)
        return 1

    findings = run_checks(cis, rels, stale_days=args.stale_days, rules=rules)
    score = health_score(cis, findings)
    text = to_csv(findings) if args.format == "csv" else WRITERS[args.format](cis, findings, score)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        logging.info("wrote %s report to %s", args.format, args.output)
    else:
        sys.stdout.write(text)
    if args.history:
        entry = append_history(args.history, len(cis), score, findings)
        logging.info("history: score %.1f (delta %s)", score, entry["delta"])
    logging.info("health score %.1f with %d findings across %d CIs", score, len(findings), len(cis))
    if args.fail_under is not None and score < args.fail_under:
        logging.warning("health score %.1f is below threshold %.1f", score, args.fail_under)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
