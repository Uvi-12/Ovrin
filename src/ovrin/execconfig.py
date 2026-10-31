"""Executing configuration: the files that make a coding agent run code.

Instruction files (AGENTS.md, CLAUDE.md) change what an agent intends. A second
family of files changes what runs: an MCP server declared in .mcp.json is a
process the agent spawns, a hook in .claude/settings.json is a shell command
the agent runs on an event. This module finds those files, decides whether an
agent launched at the repository root would load each one, extracts what each
one can do, and flags the cases that should stop a build.

The verdict is calibrated to what the activation benchmark measured, not to
the most alarming reading. Agents load these files from the root, so a copy
buried in a dependency is a warning, not a load. The case that matters is a
root file that runs code nobody reviewed, including code that lives in a
vendored or installed dependency.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from . import capabilities as caps
from .constants import SKIP_DIRS

THIRD_PARTY = frozenset({"vendored", "submodule", "installed-dependency"})

# Capabilities that mean the file can make something happen, as opposed to
# only reading an environment variable or adjusting permissions.
EXECUTING_KINDS = frozenset({"process_exec", "bundled_script", "network_egress"})

# Short labels for the terminal table.
SHORT = {
    "process_exec": "exec", "network_egress": "net", "credential_ref": "cred",
    "env_read": "env", "permission_grant": "perm", "floating_version": "float",
    "bundled_script": "script",
}

# Prefixes hook commands use to point at the project directory.
_PROJECT_VARS = re.compile(
    r"^\"?\$\{?(CLAUDE_PROJECT_DIR|GEMINI_PROJECT_DIR|PWD)\}?\"?/")


@dataclass
class ExecFormat:
    kind: str
    file: str               # path relative to the launch directory; may hold one '*'
    parsers: list[str]
    auto_exec: bool
    loaders: list[dict[str, Any]]
    note: str = ""

    def regex(self) -> re.Pattern[str]:
        body = re.escape(self.file).replace(r"\*", "[^/]+")
        return re.compile(r"^(?:(?P<dir>.+)/)?" + body + "$")


@dataclass
class ExecCatalogue:
    version: str
    verified: str
    formats: list[ExecFormat]
    not_repo_local: list[dict[str, str]] = field(default_factory=list)


def load(path: Path | None = None) -> ExecCatalogue:
    if path is not None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        text = resources.files("ovrin.data").joinpath("exec_formats.yaml").read_text("utf-8")
        raw = yaml.safe_load(text)
    fmts = [
        ExecFormat(
            kind=f["kind"], file=f["file"], parsers=list(f.get("parsers", [])),
            auto_exec=bool(f.get("autoExec", True)),
            loaders=list(f.get("loaders", [])), note=(f.get("note") or "").strip(),
        )
        for f in raw.get("formats", [])
    ]
    return ExecCatalogue(str(raw.get("version", "0")), str(raw.get("verified", "")),
                         fmts, list(raw.get("not_repo_local", [])))


def match(rel: str, formats: list[ExecFormat]) -> tuple[ExecFormat, str] | None:
    """Return the format and the launch directory ('' for the root) for a path.
    The longest matching file pattern wins, so .claude/settings.local.json is
    not mistaken for something shorter."""
    best: tuple[ExecFormat, str] | None = None
    best_len = -1
    for fmt in formats:
        m = fmt.regex().match(rel)
        if m and len(fmt.file) > best_len:
            best, best_len = (fmt, m.group("dir") or ""), len(fmt.file)
    return best


def discover(root: Path, formats: list[ExecFormat],
             max_depth: int | None = None) -> list[tuple[str, Path, ExecFormat, str]]:
    root = root.resolve()
    out = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        hit = match(rel, formats)
        if hit is None:
            continue
        fmt, launch_dir = hit
        if max_depth is not None and launch_dir and launch_dir.count("/") + 1 > max_depth:
            continue
        out.append((rel, path, fmt, launch_dir))
    return sorted(out, key=lambda t: t[0])


def extract(abs_path: Path, rel: str, fmt: ExecFormat) -> caps.CapabilityReport:
    """Union of every parser the format declares. Reads the file as data and
    never executes it."""
    merged = caps.CapabilityReport(path=rel, family=fmt.kind, parsed=True)
    errors = []
    for parser in fmt.parsers:
        if parser == "skill":
            rep = caps.extract_skill(abs_path.parent, rel, fmt.kind)
        elif parser == "mcp":
            rep = caps.extract(abs_path, rel, "mcp")
        elif parser == "settings":
            rep = caps.extract(abs_path, rel, "settings")
        else:
            continue
        if rep.parse_error and not rep.capabilities:
            errors.append(rep.parse_error)
        if not rep.parsed:
            merged.parsed = False
        merged.capabilities.extend(rep.capabilities)
    # A gemini settings file without mcpServers is not a parse failure.
    if len(fmt.parsers) > 1 and merged.capabilities:
        merged.parsed, errors = True, []
    if errors and not merged.capabilities:
        merged.parse_error = "; ".join(sorted(set(errors)))
    return merged


def _command_tokens(cap: caps.Capability) -> list[str]:
    ev = cap.evidence or {}
    parts: list[str] = []
    if ev.get("command"):
        parts.append(str(ev["command"]))
    parts.extend(str(a) for a in ev.get("args", []) or [])
    tokens: list[str] = []
    for part in parts:
        try:
            tokens.extend(shlex.split(part))
        except ValueError:
            tokens.extend(part.split())
    return tokens


def code_paths(report: caps.CapabilityReport, launch_dir: str) -> list[str]:
    """Repository-relative paths that a command in this file would execute or
    load. Only relative paths inside the repository are considered; package
    names fetched by npx or uvx are reported as floating_version instead."""
    found: set[str] = set()
    for cap in report.capabilities:
        if cap.kind not in {"process_exec"}:
            continue
        for tok in _command_tokens(cap):
            tok = _PROJECT_VARS.sub("", tok.strip("'\""))
            # '@scope/pkg' is an npm package name, not a path in this repository.
            if not tok or tok.startswith(("/", "-", "~", "@")) or "://" in tok:
                continue
            if "/" not in tok or "$" in tok:
                continue
            rel = posixpath.normpath(posixpath.join(launch_dir, tok)) if launch_dir \
                else posixpath.normpath(tok)
            if rel.startswith(".."):
                continue
            found.add(rel)
    # The skill parser reports its bundled scripts relative to the skill dir.
    for cap in report.capabilities:
        if cap.kind == "bundled_script" and (cap.evidence or {}).get("script"):
            skill_dir = posixpath.dirname(report.path)
            found.add(posixpath.normpath(posixpath.join(skill_dir, cap.evidence["script"])))
    return sorted(found)


def assess(entry: dict[str, Any]) -> dict[str, Any]:
    """The gate. 'block' reasons fail a build under --fail-on-exec-risk;
    'warn' reasons are surfaced but never fail it."""
    kinds = {c["kind"] for c in entry["capabilities"]}
    executes = bool(kinds & EXECUTING_KINDS)
    loaded = any(r["verdict"] == "loaded" for r in entry["loadedBy"].values())
    third_party_file = entry["origin"]["class"] in THIRD_PARTY
    enforceable = entry["review"]["enforceable"]
    reasons: list[dict[str, str]] = []

    if loaded and executes and entry["autoExec"]:
        if enforceable is False:
            reasons.append({"severity": "block", "code": "unreviewed-exec",
                            "detail": "runs code when the agent opens the repository, "
                                      "and no enforced review covers this file"})
        for tp in entry["runsThirdPartyCode"]:
            reasons.append({"severity": "block", "code": "third-party-code",
                            "detail": f"runs {tp['origin']} code at {tp['path']}, "
                                      "outside the project's own reviewed source"})
        if third_party_file:
            reasons.append({"severity": "block", "code": "third-party-config",
                            "detail": f"the file itself is {entry['origin']['class']} "
                                      "and loads at the repository root"})
    if loaded and executes and not entry["autoExec"] and (
            enforceable is False or entry["runsThirdPartyCode"] or third_party_file):
        reasons.append({"severity": "warn", "code": "model-invoked-exec",
                        "detail": "bundles code the model can choose to run, "
                                  "without enforced review"})
    if not loaded and executes and third_party_file:
        reasons.append({"severity": "warn", "code": "nested-third-party",
                        "detail": f"{entry['origin']['class']} executing configuration; "
                                  f"loaded only if an agent is launched in "
                                  f"{entry['launchDir'] or '.'}"})
    if loaded and "floating_version" in kinds:
        reasons.append({"severity": "warn", "code": "floating-version",
                        "detail": "runs a package version that can change without a commit"})
    if not entry["parsed"]:
        reasons.append({"severity": "warn", "code": "unparsed",
                        "detail": entry.get("parseError") or "could not be parsed"})
    return {"blocked": any(r["severity"] == "block" for r in reasons), "reasons": reasons}
