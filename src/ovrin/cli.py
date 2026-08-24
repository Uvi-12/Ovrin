"""Command line interface for Ovrin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .harness import Rules
from .manifest import build
from .report import render
from .spdx import to_spdx

OK, FINDINGS, ERROR = 0, 1, 2


def _scan(a: argparse.Namespace) -> int:
    root = Path(a.path)
    if not root.is_dir():
        print(f"ovrin: not a directory: {root}", file=sys.stderr)
        return ERROR
    rules = Rules.load(Path(a.rules) if a.rules else None)
    m = build(root, rules, max_depth=a.max_depth, no_timestamp=a.no_timestamp)
    if a.format == "json":
        payload = json.dumps(m, indent=2)
    elif a.format == "spdx":
        payload = json.dumps(to_spdx(m, name=root.name), indent=2)
    else:
        payload = render(m, color=False if a.no_color else None)
    if a.output:
        Path(a.output).write_text(payload + "\n", encoding="utf-8")
        print(f"ovrin: wrote {a.output}", file=sys.stderr)
    else:
        print(payload)
    if a.fail_on_third_party and m["summary"]["thirdParty"]:
        return FINDINGS
    if a.fail_on_unreviewed and m["summary"]["notReviewEnforced"]:
        return FINDINGS
    return OK


def _harnesses(a: argparse.Namespace) -> int:
    rules = Rules.load(Path(a.rules) if a.rules else None)
    print(f"loading matrix v{rules.version} (verified {rules.verified})\n")
    print("  Confidence is per behavioural claim. Only 'observed' claims have")
    print("  been run against the real agent.\n")
    for h in rules.harnesses:
        print(f"  {h.id}")
        for claim, d in (h.claims or {}).items():
            print(f"      {claim:<20} {str(d.get('value')):<12} {d.get('confidence')}")
    print()
    return OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ovrin",
        description="Inventory the instruction files your coding agent reads as configuration.")
    p.add_argument("--version", action="version", version=f"ovrin {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("scan", help="scan a directory and emit a manifest")
    sc.add_argument("path", nargs="?", default=".")
    sc.add_argument("-f", "--format", choices=("table", "json", "spdx"), default="table")
    sc.add_argument("-o", "--output")
    sc.add_argument("--rules")
    sc.add_argument("--max-depth", type=int, default=None)
    sc.add_argument("--no-timestamp", action="store_true",
                    help="omit generatedAt, for reproducible output")
    sc.add_argument("--no-color", action="store_true")
    sc.add_argument("--fail-on-third-party", action="store_true")
    sc.add_argument("--fail-on-unreviewed", action="store_true")
    sc.set_defaults(func=_scan)

    hs = sub.add_parser("harnesses", help="print the loading matrix")
    hs.add_argument("--rules")
    hs.set_defaults(func=_harnesses)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return ERROR


if __name__ == "__main__":
    raise SystemExit(main())
