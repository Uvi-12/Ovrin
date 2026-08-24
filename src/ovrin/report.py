"""Human-readable terminal output."""

from __future__ import annotations

import sys
from typing import Any

R, B, D = "\033[0m", "\033[1m", "\033[2m"
RED, YEL, GRN, CYN = "\033[31m", "\033[33m", "\033[32m", "\033[36m"
OCOL = {"repo": GRN, "workspace": CYN, "vendored": RED, "submodule": RED,
        "installed-dependency": RED, "untracked": YEL, "unknown": YEL}


def _c(t, col, on): return f"{col}{t}{R}" if on else t


def render(m: dict[str, Any], color: bool | None = None) -> str:
    if color is None:
        color = sys.stdout.isatty()
    o, s, subj = [], m["summary"], m["subject"]
    o.append(_c("Agent instruction manifest", B, color))
    o.append(f"  subject      {subj['path']}")
    o.append(f"  codeowners   {subj['codeownersPath'] or _c('none found', YEL, color)}")
    o.append(f"  rules        harnesses v{m['harnessRules']['version']} "
             f"(verified {m['harnessRules']['verified']})")
    o.append("")
    if not m["instructions"]:
        o.append("  No agent instruction files found.")
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
    o.append(_c("Summary", B, color))
    o.append(f"  instruction files    {s['total']}")
    o.append(f"  third-party origin   {tp}")
    o.append(f"  not review-enforced  {nre}")
    o.append(f"  first commit by author  {s['introducedInAuthorsFirstCommit']}")
    o.append(f"  git-ignored path     {s['gitIgnored']}")
    o.append("")
    o.append(_c("  '?' marks a harness whose behaviour we have not verified.", D, color))
    o.append(_c("  See docs/loading-matrix.md before citing any verdict.", D, color))
    return "\n".join(o)
