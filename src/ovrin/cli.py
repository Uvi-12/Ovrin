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
    quiet = a.format == "table"   # the table already shows why
    failed = False
    if a.fail_on_third_party and m["summary"]["thirdParty"]:
        failed = True
        if not quiet:
            for e in m["instructions"]:
                if e["origin"]["class"] in {"vendored", "submodule", "installed-dependency"}:
                    print(f"ovrin: THIRD-PARTY {e['path']} ({e['origin']['class']})",
                          file=sys.stderr)
    if a.fail_on_unreviewed and m["summary"]["notReviewEnforced"]:
        failed = True
        if not quiet:
            for e in m["instructions"]:
                if e["review"]["enforceable"] is not True:
                    print(f"ovrin: UNREVIEWED {e['path']}: {e['review']['reason']}",
                          file=sys.stderr)
    if a.fail_on_exec_risk and m["summary"]["executing"]["blocked"]:
        failed = True
        if not quiet:
            for e in m["executing"]:
                for r in e["risk"]["reasons"]:
                    if r["severity"] == "block":
                        print(f"ovrin: BLOCK {e['path']}: {r['detail']}", file=sys.stderr)
    if failed:
        return FINDINGS
    return OK


def _enforce(a: argparse.Namespace) -> int:
    """Three-layer enforcement gate: static pre-flight, import-delegation
    audit, and uncertainty disclosure."""
    from .enforce import enforce_all, quarantine, to_sarif

    root = Path(a.path).resolve()
    if not root.is_dir():
        print(f"ovrin: not a directory: {root}", file=sys.stderr)
        return ERROR

    rules = Rules.load(Path(a.rules) if a.rules else None)
    m = build(root, rules, no_timestamp=True)

    policy = None
    if getattr(a, "policy", None):
        from .delegation import PolicyError, load_policy
        try:
            policy = load_policy(Path(a.policy).resolve())
        except PolicyError as e:
            print(f"ovrin: policy error: {e}", file=sys.stderr)
            return ERROR
    ctx = getattr(a, "context_path", None) or "."
    result = enforce_all(m, harness_id=a.harness, root=root,
                        policy=policy, context_path=ctx)

    if a.format == "sarif":
        payload = json.dumps(to_sarif(result, tool_version=__version__), indent=2)
        if a.output:
            Path(a.output).write_text(payload + "\n", encoding="utf-8")
            print(f"ovrin: wrote SARIF to {a.output}", file=sys.stderr)
        else:
            print(payload)
    elif a.format == "json":
        out = {
            "harness": result.harness_id,
            "summary": result.summary_line(),
            "decisions": [
                {"path": d.path, "action": d.action, "layer": d.layer,
                 "reason": d.reason,
                 "resolverConfidence": d.uncertainty.resolver_confidence}
                for d in result.decisions
            ],
            "importDelegations": [
                {"importer": i.importer_path, "target": i.import_target,
                 "resolved": i.resolved_target, "action": i.action,
                 "reason": i.reason,
                 "importChainComplete": i.uncertainty.import_chain_complete}
                for i in result.import_delegations
            ],
        }
        payload = json.dumps(out, indent=2)
        if a.output:
            Path(a.output).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
    else:
        # Table output
        print(f"\novrin enforce  harness={a.harness}\n")
        print("LAYER 1 — STATIC PRE-FLIGHT GATE")
        for d in result.decisions:
            if d.action != "ALLOW":
                print(f"  {d}")
        blocked_paths = [d.path for d in result.decisions if d.action == "BLOCK"]
        warned_paths = [d.path for d in result.decisions if d.action == "WARN"]
        if not blocked_paths and not warned_paths:
            print("  (no findings)")

        print("\nLAYER 2 — IMPORT-DELEGATION AUDIT")
        for imp in result.import_delegations:
            if imp.action != "OK":
                print(f"  {imp.action:5s}  {imp.importer_path}"
                      f"  imports→{imp.resolved_target or imp.import_target}"
                      f"  ({imp.reason})")
        if not any(i.action != "OK" for i in result.import_delegations):
            print("  (no findings)")

        print("\nLAYER 3 — UNCERTAINTY DISCLOSURE")
        print(f"  low-confidence decisions:    {result.low_confidence_decisions}")
        print(f"  unresolved import chains:    {result.unresolved_import_chains}")

        print(f"\n{result.summary_line()}\n")

    if result.has_findings():
        if a.strip and result.blocked > 0:
            qdir = (Path(a.quarantine_dir) if a.quarantine_dir
                    else root / ".ovrin-quarantine")
            moved = quarantine(root, result, qdir)
            print(f"ovrin: quarantined {len(moved)} file(s) to {qdir}",
                  file=sys.stderr)
        elif not a.strip and result.blocked > 0:
            print("ovrin: run with --strip to quarantine blocked files.",
                  file=sys.stderr)
        return FINDINGS

    return OK


def _harnesses(a: argparse.Namespace) -> int:
    rules = Rules.load(Path(a.rules) if a.rules else None)
    print(f"loading matrix v{rules.version} (matrix dated {rules.verified})\n")
    print("  Confidence is per behavioural claim. Only 'observed' claims have")
    print("  been run against the real agent.\n")
    tally: dict[str, int] = {}
    for h in rules.harnesses:
        for d in (h.claims or {}).values():
            c = str(d.get("confidence", "unknown"))
            tally[c] = tally.get(c, 0) + 1
    total = sum(tally.values())
    print(f"  claim coverage: {tally.get('observed', 0)} observed, "
          f"{tally.get('documented', 0)} documented, "
          f"{tally.get('inferred', 0)} inferred, "
          f"{tally.get('unknown', 0)} unknown (of {total})\n")
    for h in rules.harnesses:
        print(f"  {h.id}")
        for claim, d in (h.claims or {}).items():
            print(f"      {claim:<20} {str(d.get('value')):<12} {d.get('confidence')}")
    print()
    from .execconfig import load as load_exec
    cat = load_exec()
    print(f"executing configuration v{cat.version} (dated {cat.verified})\n")
    print("  Loaded from the directory the agent is launched in (the repository root).\n")
    for f in cat.formats:
        auto = "auto" if f.auto_exec else "model-invoked"
        for ld in f.loaders:
            print(f"  {f.file:<30} {ld['harness']:<14} {auto:<14} {ld.get('confidence')}")
    for n in cat.not_repo_local:
        print(f"  {'(none in repository)':<30} {n['harness']:<14} {'-':<14} {n['reason']}")
    print()
    return OK


def _keygen(a: argparse.Namespace) -> int:
    from .signing import generate_keypair
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    priv, pub = out / "ovrin-signing.key", out / "ovrin-signing.pub"
    if (priv.exists() or pub.exists()) and not a.force:
        print(f"ovrin: {priv} or {pub} exists; use --force", file=sys.stderr)
        return ERROR
    generate_keypair(priv, pub)
    print(f"ovrin: wrote {priv} (private) and {pub} (public)", file=sys.stderr)
    return OK


def _sign(a: argparse.Namespace) -> int:
    from .signing import sign_manifest
    mpath = Path(a.manifest)
    if not mpath.is_file():
        print(f"ovrin: not a file: {mpath}", file=sys.stderr)
        return ERROR
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    sig = sign_manifest(manifest, Path(a.key))
    out = Path(a.output) if a.output else mpath.with_suffix(mpath.suffix + ".sig")
    out.write_text(json.dumps(sig, indent=2) + "\n", encoding="utf-8")
    print(f"ovrin: wrote signature to {out}", file=sys.stderr)
    return OK


def _verify(a: argparse.Namespace) -> int:
    from .signing import verify_manifest
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    sig = json.loads(Path(a.sig).read_text(encoding="utf-8"))
    pub = Path(a.pub).read_text(encoding="utf-8").strip() if a.pub else None
    ok = verify_manifest(manifest, sig, public_key_hex=pub)
    print("ovrin: signature VALID" if ok else "ovrin: signature INVALID",
          file=sys.stderr)
    return OK if ok else FINDINGS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ovrin",
        description="Inventory and gate the configuration your coding agent reads and runs.")
    p.add_argument("--version", action="version", version=f"ovrin {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("scan", help="scan a directory and emit a manifest")
    sc.add_argument("path", nargs="?", default=".")
    sc.add_argument("-f", "--format", choices=("table", "json", "spdx"), default="table")
    sc.add_argument("-o", "--output")
    sc.add_argument("--rules")
    sc.add_argument("--max-depth", type=int, default=None)
    sc.add_argument("--no-timestamp", action="store_true")
    sc.add_argument("--no-color", action="store_true")
    sc.add_argument("--fail-on-third-party", action="store_true")
    sc.add_argument("--fail-on-unreviewed", action="store_true")
    sc.add_argument("--fail-on-exec-risk", action="store_true",
                    help="fail when executing configuration that loads at the root "
                         "runs code without enforced review, or runs third-party code")
    sc.set_defaults(func=_scan)

    en = sub.add_parser("enforce",
                         help="three-layer enforcement: static gate + import "
                              "audit + uncertainty disclosure")
    en.add_argument("path", nargs="?", default=".",
                     help="repository root (default: current directory)")
    en.add_argument("--harness", required=True,
                     help="harness id, e.g. claude-code or codex-cli")
    en.add_argument("--rules", default=None)
    en.add_argument("-f", "--format",
                     choices=("table", "json", "sarif"), default="table",
                     help="output format; sarif for CI integration")
    en.add_argument("-o", "--output", default=None,
                     help="write output to this file instead of stdout")
    en.add_argument("--strip", action="store_true",
                     help="quarantine BLOCK-ed files before agent launch")
    en.add_argument("--quarantine-dir", default=None,
                     help="quarantine destination (default: .ovrin-quarantine)")
    en.add_argument("--policy", default=None,
                     help="path to authority-policy.yaml declaring D(s,c); "
                          "when supplied, Ovrin evaluates the paper's IAD "
                          "definition (A_h=1 ^ D=0) directly, instead of the "
                          "three-condition heuristic")
    en.add_argument("--context-path", default=".",
                     help="the context path c passed to D(s,c); default '.'")
    en.set_defaults(func=_enforce)

    hs = sub.add_parser("harnesses", help="print the loading matrix")
    hs.add_argument("--rules")
    hs.set_defaults(func=_harnesses)
    kg = sub.add_parser("keygen", help="generate an Ed25519 signing keypair")
    kg.add_argument("--out-dir", default=".")
    kg.add_argument("--force", action="store_true")
    kg.set_defaults(func=_keygen)

    sg = sub.add_parser("sign", help="sign a manifest JSON with an Ed25519 key")
    sg.add_argument("manifest")
    sg.add_argument("--key", required=True, help="path to the private key")
    sg.add_argument("-o", "--output", default=None)
    sg.set_defaults(func=_sign)

    vf = sub.add_parser("verify", help="verify a manifest against its signature")
    vf.add_argument("manifest")
    vf.add_argument("--sig", required=True, help="path to the .sig file")
    vf.add_argument("--pub", default=None, help="pin the signer's public key file")
    vf.set_defaults(func=_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return ERROR


if __name__ == "__main__":
    raise SystemExit(main())
