"""CLI: python -m cmdb_dq --input sample_data/cmdb_export.json --format md"""
from __future__ import annotations

import argparse
import logging
import sys

from .checks import health_score, run_checks
from .report import to_json, to_markdown
from .source import SourceError, TableApiSource, load_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cmdb_dq", description="CMDB data-quality checks (CSDM-style)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="JSON export with cmdb_ci and cmdb_rel_ci arrays")
    src.add_argument("--live", action="store_true", help="read from instance using SN_* environment variables")
    ap.add_argument("--query", default="", help="encoded query to scope CIs in live mode")
    ap.add_argument("--stale-days", type=int, default=30)
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--fail-under", type=float, default=None, help="exit 2 if health score is below this value")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    try:
        cis, rels = load_file(args.input) if args.input else TableApiSource.from_env().load(args.query)
    except SourceError as exc:
        logging.error("%s", exc)
        return 1

    findings = run_checks(cis, rels, stale_days=args.stale_days)
    score = health_score(cis, findings)
    print(to_markdown(cis, findings, score) if args.format == "md" else to_json(cis, findings, score))
    if args.fail_under is not None and score < args.fail_under:
        logging.warning("health score %.1f is below threshold %.1f", score, args.fail_under)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
