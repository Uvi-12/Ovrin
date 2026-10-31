"""Assemble the agent configuration manifest: instruction files, and the
executing configuration (MCP servers, hooks, skills) that makes an agent run
code."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from . import __version__, execconfig, gitmeta
from .codeowners import Owners
from .discovery import _hash, scan
from .formats import load as load_formats
from .harness import Rules, reachability
from .origin import classify

SCHEMA_VERSION = "0.2.0"


def _review(owners, source, *, tracked, ignored, origin_cls) -> dict[str, Any]:
    # A CODEOWNERS rule matching a path is not the same as review happening. A
    # catch-all '*' matches ignored and untracked files that no pull request
    # ever touches. So ruleMatches and enforceable are separate, and
    # enforceable can be null when it depends on branch protection we cannot see.
    if not source:
        return {"codeowners": [], "ruleMatches": False, "enforceable": False,
                "reason": "no CODEOWNERS file in this repository", "source": None}
    if ignored:
        return {"codeowners": list(owners), "ruleMatches": bool(owners), "enforceable": False,
                "reason": "path is git-ignored; it never appears in a pull request diff",
                "source": source}
    if not tracked:
        return {"codeowners": list(owners), "ruleMatches": bool(owners), "enforceable": False,
                "reason": "path is untracked; not part of any review surface", "source": source}
    if not owners:
        return {"codeowners": [], "ruleMatches": False, "enforceable": False,
                "reason": "tracked, but no CODEOWNERS rule matches this path", "source": source}
    return {"codeowners": list(owners), "ruleMatches": True, "enforceable": None,
            "reason": "rule matches a tracked path; enforcement depends on branch protection",
            "source": source}


def build(root: Path, rules: Rules | None = None, *, max_depth: int | None = None,
          no_timestamp: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    rules = rules or Rules.load()
    formats = load_formats()
    owners = Owners.load(root)

    found = scan(root, formats, max_depth=max_depth)
    tracked = gitmeta.tracked_files(root)
    submodules = gitmeta.submodule_paths(root)
    ignored = gitmeta.ignored(root, tuple(f.rel_path for f in found))

    entries = []
    for f in found:
        origin = classify(root, f.rel_path, rules.vendor_markers, tracked, submodules)
        g = gitmeta.file_git(root, f.rel_path)
        owner_list = owners.owners_for(f.rel_path)
        first_commit_intro = gitmeta.introduced_in_authors_first_commit(
            root, f.rel_path, g.first_author)

        reach = {}
        for h in rules.harnesses:
            verdict, reason = reachability(
                h, f.rel_path, is_ignored=f.rel_path in ignored, origin_cls=origin.cls)
            if verdict == "not-discovered":
                continue
            reach[h.id] = {"verdict": verdict, "reason": reason, "confidence": h.confidence}

        entries.append({
            "path": f.rel_path,
            "family": f.family,
            "activation": f.activation,
            "digest": f.digest,
            "digestStatus": f.digest_status,
            "bytes": f.bytes,
            "origin": {"class": origin.cls, "container": origin.container,
                       "package": origin.package, "evidence": origin.evidence},
            "review": _review(owner_list, owners.source, tracked=g.tracked,
                              ignored=f.rel_path in ignored, origin_cls=origin.cls),
            "introducedInAuthorsFirstCommit": first_commit_intro,
            "git": {"tracked": g.tracked, "lastCommit": g.last_commit,
                    "lastAuthor": g.last_author, "lastModified": g.last_date,
                    "firstCommit": g.first_commit, "firstAuthor": g.first_author},
            "gitIgnored": f.rel_path in ignored,
            "reachability": reach,
        })

    third = [e for e in entries if e["origin"]["class"] in
             {"vendored", "submodule", "installed-dependency"}]
    unrev = [e for e in entries if e["review"]["enforceable"] is not True]

    catalogue = execconfig.load()
    executing = _executing(root, catalogue, rules, owners, tracked, submodules,
                           max_depth=max_depth)

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "tool": {"name": "ovrin", "version": __version__},
        "harnessRules": {"version": rules.version, "verified": rules.verified},
        "subject": {"path": str(root), "isGitRepository": gitmeta.is_repo(root),
                    "codeownersPresent": owners.present, "codeownersPath": owners.source},
        "execRules": {"version": catalogue.version, "verified": catalogue.verified,
                      "notRepoLocal": catalogue.not_repo_local},
        "instructions": entries,
        "executing": executing,
        "summary": {
            "total": len(entries),
            "byOrigin": _count(entries, lambda e: e["origin"]["class"]),
            "byFamily": _count(entries, lambda e: e["family"]),
            "thirdParty": len(third),
            "notReviewEnforced": len(unrev),
            "gitIgnored": sum(1 for e in entries if e["gitIgnored"]),
            "introducedInAuthorsFirstCommit":
                sum(1 for e in entries if e["introducedInAuthorsFirstCommit"] is True),
            "executing": _exec_summary(executing),
        },
    }
    if not no_timestamp:
        manifest["generatedAt"] = _dt.datetime.now(_dt.timezone.utc).replace(
            microsecond=0).isoformat()
    return manifest


def _count(entries, key) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in entries:
        out[key(e)] = out.get(key(e), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _executing(root, catalogue, rules, owners, tracked, submodules, *, max_depth):
    found = execconfig.discover(root, catalogue.formats, max_depth=max_depth)
    ignored = gitmeta.ignored(root, tuple(rel for rel, *_ in found))
    out = []
    for rel, path, fmt, launch_dir in found:
        try:
            digest, size, status = _hash(path)
        except OSError:
            digest, size, status = None, 0, "unreadable"
        origin = classify(root, rel, rules.vendor_markers, tracked, submodules)
        g = gitmeta.file_git(root, rel)
        report = execconfig.extract(path, rel, fmt)

        loaded_by = {}
        for ld in fmt.loaders:
            if launch_dir == "":
                loaded_by[ld["harness"]] = {
                    "verdict": "loaded", "confidence": ld.get("confidence", "unknown"),
                    "reason": "at the repository root, where the agent is launched",
                    "source": ld.get("source", "")}
            else:
                loaded_by[ld["harness"]] = {
                    "verdict": "not-discovered", "confidence": ld.get("confidence", "unknown"),
                    "reason": f"loaded only if the agent is launched in {launch_dir}",
                    "source": ld.get("source", "")}

        runs_tp = []
        for cp in execconfig.code_paths(report, launch_dir):
            o = classify(root, cp, rules.vendor_markers, tracked, submodules)
            if o.cls in execconfig.THIRD_PARTY:
                runs_tp.append({"path": cp, "origin": o.cls, "container": o.container,
                                "package": o.package})

        entry = {
            "path": rel,
            "kind": fmt.kind,
            "autoExec": fmt.auto_exec,
            "launchDir": launch_dir,
            "digest": digest,
            "digestStatus": status,
            "bytes": size,
            "origin": {"class": origin.cls, "container": origin.container,
                       "package": origin.package, "evidence": origin.evidence},
            "review": _review(owners.owners_for(rel), owners.source, tracked=g.tracked,
                              ignored=rel in ignored, origin_cls=origin.cls),
            "git": {"tracked": g.tracked, "lastCommit": g.last_commit,
                    "lastAuthor": g.last_author, "lastModified": g.last_date,
                    "firstCommit": g.first_commit, "firstAuthor": g.first_author},
            "gitIgnored": rel in ignored,
            "loadedBy": loaded_by,
            "parsed": report.parsed,
            "parseError": report.parse_error,
            "capabilities": [{"kind": c.kind, "detail": c.detail} for c in report.capabilities],
            "runsThirdPartyCode": runs_tp,
        }
        entry["risk"] = execconfig.assess(entry)
        out.append(entry)
    return out


def _exec_summary(executing) -> dict:
    caps: dict[str, int] = {}
    for e in executing:
        for k in {c["kind"] for c in e["capabilities"]}:
            caps[k] = caps.get(k, 0) + 1
    loaded = [e for e in executing
              if any(r["verdict"] == "loaded" for r in e["loadedBy"].values())]
    return {
        "total": len(executing),
        "loadedAtRoot": len(loaded),
        "canExecute": sum(1 for e in executing
                          if {c["kind"] for c in e["capabilities"]} & execconfig.EXECUTING_KINDS),
        "thirdPartyOrigin": sum(1 for e in executing
                                if e["origin"]["class"] in execconfig.THIRD_PARTY),
        "runsThirdPartyCode": sum(1 for e in executing if e["runsThirdPartyCode"]),
        "notReviewEnforced": sum(1 for e in executing if e["review"]["enforceable"] is not True),
        "blocked": sum(1 for e in executing if e["risk"]["blocked"]),
        "byCapability": dict(sorted(caps.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
