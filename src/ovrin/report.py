"""Human-readable terminal output."""

from __future__ import annotations

import sys
from typing import Any

from .execconfig import SHORT

R, B, D = "\033[0m", "\033[1m", "\033[2m"
RED, YEL, GRN, CYN = "\033[31m", "\033[33m", "\033[32m", "\033[36m"
OCOL = {"repo": GRN, "workspace": CYN, "vendored": RED, "submodule": RED,
        "installed-dependency": RED, "untracked": YEL, "unknown": YEL}


def _c(t, col, on): return f"{col}{t}{R}" if on else t


def render(m: dict[str, Any], color: bool | None = None) -> str:
    if color is None:
        color = sys.stdout.isatty()
    o, s, subj = [], m["summary"], m["subject"]
    o.append(_c("Agent configuration manifest", B, color))
    o.append(f"  subject      {subj['path']}")
    o.append(f"  codeowners   {subj['codeownersPath'] or _c('none found', YEL, color)}")
    o.append(f"  rules        harnesses v{m['harnessRules']['version']} "
             f"(matrix dated {m['harnessRules']['verified']}, documented)")
    if m.get("execRules"):
        o.append(f"               executing config v{m['execRules']['version']} "
                 f"(dated {m['execRules']['verified']}; see `ovrin harnesses`)")
    o.append("")
    o.append(_c("Instruction files", B, color))
    if not m["instructions"]:
        o.append("  No agent instruction files found.")
        o.append("")
        o.extend(_executing(m, color))
        return "\n".join(o)
    w = min(max((len(e["path"]) for e in m["instructions"]), default=20), 58)
    o.append(_c(f"  {'PATH':<{w}}  {'ORIGIN':<20}  {'REVIEW':<11}  LOADED BY", D, color))
    for e in m["instructions"]:
        p = e["path"] if len(e["path"]) <= w else "..." + e["path"][-(w - 3):]
        oc = e["origin"]["class"]
        enf = e["review"]["enforceable"]
        rev = "enforced?" if enf is None else ("no" if enf is False else "yes")
        rev_c = rev if enf is None else _c(rev, YEL if not enf else GRN, color)
        loaders = [h for h, r in e["reachability"].items() if r["verdict"] == "loaded"]
        unver = [h for h, r in e["reachability"].items() if r["verdict"] == "unverified"]
        cell = ",".join(loaders) if loaders else "-"
        if unver:
            cell += f" (?{','.join(unver)})"
        o.append(f"  {p:<{w}}  {_c(oc.ljust(20), OCOL.get(oc, ''), color)}  "
                 f"{rev_c}{' ' * max(0, 11 - len(rev))}  {cell}")
    o.append("")
    tp = _c(str(s["thirdParty"]), RED if s["thirdParty"] else GRN, color)
    nre = _c(str(s["notReviewEnforced"]), YEL if s["notReviewEnforced"] else GRN, color)
    o.extend(_executing(m, color))
    o.append(_c("Summary", B, color))
    o.append(f"  instruction files    {s['total']}")
    o.append(f"  third-party origin   {tp}")
    o.append(f"  not review-enforced  {nre}")
    o.append(f"  first commit by author  {s['introducedInAuthorsFirstCommit']}")
    o.append(f"  git-ignored path     {s['gitIgnored']}")
    x = s.get("executing") or {}
    if x.get("total"):
        blk = _c(str(x["blocked"]), RED if x["blocked"] else GRN, color)
        o.append(f"  executing config     {x['total']}  "
                 f"(loaded at root {x['loadedAtRoot']}, can run code {x['canExecute']})")
        o.append(f"  runs third-party code  {x['runsThirdPartyCode']}")
        o.append(f"  exec-risk findings   {blk} blocking")
    o.append("")
    o.append(_c("  '?' marks a harness whose behaviour we have not verified.", D, color))
    o.append(_c("  See docs/loading-matrix.md before citing any verdict.", D, color))
    return "\n".join(o)


def _executing(m: dict[str, Any], color: bool) -> list[str]:
    ex = m.get("executing") or []
    o = [_c("Executing configuration", B, color)]
    if not ex:
        o += ["  No executing agent configuration found (.mcp.json, hooks, skills).", ""]
        return o
    w = min(max((len(e["path"]) for e in ex), default=20), 58)
    head = f"  {'PATH':<{w}}  {'ORIGIN':<20}  {'REVIEW':<11}  {'LOADED BY':<22}  CAN"
    o.append(_c(head, D, color))
    for e in ex:
        p = e["path"] if len(e["path"]) <= w else "..." + e["path"][-(w - 3):]
        oc = e["origin"]["class"]
        enf = e["review"]["enforceable"]
        rev = "enforced?" if enf is None else ("no" if enf is False else "yes")
        rev_c = rev if enf is None else _c(rev, YEL if not enf else GRN, color)
        loaders = [h for h, r in e["loadedBy"].items() if r["verdict"] == "loaded"]
        cell = ",".join(loaders) if loaders else "- (not at root)"
        kinds = sorted({c["kind"] for c in e["capabilities"]})
        can = ",".join(SHORT.get(k, k) for k in kinds) or "-"
        o.append(f"  {p:<{w}}  {_c(oc.ljust(20), OCOL.get(oc, ''), color)}  "
                 f"{rev_c}{' ' * max(0, 11 - len(rev))}  {cell:<22}  {can}")
    findings = [(e["path"], r) for e in ex for r in e["risk"]["reasons"]]
    if findings:
        o.append("")
        for path, r in findings:
            tag = _c("BLOCK", RED, color) if r["severity"] == "block" else _c("warn ", YEL, color)
            o.append(f"  {tag}  {path}: {r['detail']}")
    nrl = (m.get("execRules") or {}).get("notRepoLocal") or []
    if nrl:
        o.append(_c("  Not repository-local: " + ", ".join(n["harness"] for n in nrl)
                    + " (executing config is global, so a committed file cannot inject it).",
                    D, color))
    o.append("")
    return o
