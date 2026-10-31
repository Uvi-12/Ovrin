"""Capability extraction for the executing agent-config surface.

Instruction files (CLAUDE.md, AGENTS.md) change what an agent *intends*. The
rest of the agent-config surface changes what *runs*: an .mcp.json server
spawns a process, a hook runs a shell command, a skill ships a script, a
settings file widens what the agent may do without asking.

This module answers one question per config file, as *facts* a reviewer can
act on, never as an intent verdict: what can this authority do?

  process_exec     a command the harness will execute (MCP server, hook)
  network_egress   a remote endpoint the config reaches (MCP url, url in a cmd)
  env_read         environment variables the config pulls into that process
  credential_ref   env_read whose name matches a secret-shaped pattern
  permission_grant an allow/deny rule that changes what runs without asking
  floating_version an exec whose package/version is unpinned (npx -y x@latest)
  bundled_script   a skill/plugin that ships an executable file

Extraction is deterministic and offline. It reads the file as data; it never
executes it. Deciding whether a capability is *malicious* remains a person's
job — this module only makes the capability visible before the agent starts.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Families whose files declare executable capability, keyed to how we parse
# them. Discovery still finds these; this map says "also extract capability".
MCP_FAMILIES = frozenset({"mcp"})
SETTINGS_FAMILIES = frozenset({"claude-settings", "settings"})
SKILL_FAMILIES = frozenset({"skill", "plugin"})

# Env var names that look like a secret. Facts, not proof: a reviewer still
# decides. Kept deliberately broad because the point is to surface, not judge.
_SECRET_RE = re.compile(
    r"(TOKEN|KEY|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|APIKEY|ACCESS|"
    r"PRIVATE|SESSION|COOKIE|DSN|CONN|DATABASE_URL|BEARER)",
    re.IGNORECASE,
)

# A floating version: a package reference with no pinned version, or an
# explicit moving tag. npx -y foo, npx foo@latest, uvx foo, pip install foo.
_FLOATING_RE = re.compile(r"@(latest|next|canary|beta|\*)\b", re.IGNORECASE)

# A URL anywhere in a string.
_URL_RE = re.compile(r"https?://[^\s'\"]+", re.IGNORECASE)

# A $VAR or ${VAR} reference inside a command string.
_SHELL_VAR_RE = re.compile(r"\$\{?([A-Z_][A-Z0-9_]*)\}?")

# File shapes that indicate a skill/plugin ships executable code.
_SCRIPT_EXT = frozenset({
    ".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".cjs", ".ts",
    ".rb", ".pl", ".ps1", ".php", ".lua",
})


@dataclass(frozen=True)
class Capability:
    kind: str                 # one of the capability kinds above
    detail: str               # human-readable fact
    evidence: dict[str, Any] = field(default_factory=dict)  # structured fields

    def __str__(self) -> str:
        return f"{self.kind}: {self.detail}"


@dataclass
class CapabilityReport:
    path: str                 # repo-relative path of the config file
    family: str
    parsed: bool              # did the file parse as the expected shape
    parse_error: str | None = None
    capabilities: list[Capability] = field(default_factory=list)

    @property
    def kinds(self) -> set[str]:
        return {c.kind for c in self.capabilities}

    def executes(self) -> bool:
        """True if this config can cause a process to run."""
        return bool(self.kinds & {"process_exec", "bundled_script"})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _is_secret(name: str) -> bool:
    return _SECRET_RE.search(name) is not None


def _env_capabilities(env: dict[str, Any], where: str) -> list[Capability]:
    caps: list[Capability] = []
    for var in sorted(env):
        kind = "credential_ref" if _is_secret(var) else "env_read"
        caps.append(Capability(
            kind,
            f"{where} reads environment variable {var}",
            {"var": var, "value_template": str(env.get(var, ""))},
        ))
    return caps


def _command_capabilities(cmd: str, where: str) -> list[Capability]:
    """Pull facts out of a raw command string (hook command, or joined argv)."""
    caps: list[Capability] = []
    if _FLOATING_RE.search(cmd):
        caps.append(Capability(
            "floating_version",
            f"{where} runs an unpinned package: {cmd!r}",
            {"command": cmd},
        ))
    for url in _URL_RE.findall(cmd):
        caps.append(Capability(
            "network_egress",
            f"{where} reaches {url}",
            {"url": url, "command": cmd},
        ))
    for var in sorted(set(_SHELL_VAR_RE.findall(cmd))):
        kind = "credential_ref" if _is_secret(var) else "env_read"
        caps.append(Capability(
            kind,
            f"{where} references environment variable {var}",
            {"var": var, "command": cmd},
        ))
    return caps


# ---------------------------------------------------------------------------
# .mcp.json  (Model Context Protocol server declarations)
# ---------------------------------------------------------------------------

def extract_mcp(text: str, rel_path: str, family: str) -> CapabilityReport:
    rep = CapabilityReport(path=rel_path, family=family, parsed=False)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        rep.parse_error = f"not valid JSON: {exc}"
        return rep
    rep.parsed = True

    servers = {}
    if isinstance(data, dict):
        # Both the Claude Code (.mcp.json) and VS Code (mcp.json) shapes.
        servers = data.get("mcpServers") or data.get("servers") or {}
    if not isinstance(servers, dict):
        rep.parse_error = "no mcpServers/servers object"
        return rep

    for name, spec in servers.items():
        if not isinstance(spec, dict):
            continue
        where = f"MCP server {name!r}"

        # Local (stdio) server: command + args spawn a process.
        command = spec.get("command")
        if command:
            args = spec.get("args") or []
            argv = [str(command)] + [str(a) for a in args]
            joined = " ".join(shlex.quote(a) for a in argv)
            rep.capabilities.append(Capability(
                "process_exec",
                f"{where} spawns a process: {joined}",
                {"command": str(command), "args": [str(a) for a in args],
                 "transport": "stdio"},
            ))
            rep.capabilities.extend(_command_capabilities(joined, where))

        # Remote (http/sse) server: a URL is reached.
        url = spec.get("url")
        if url:
            rep.capabilities.append(Capability(
                "network_egress",
                f"{where} connects to remote endpoint {url}",
                {"url": str(url), "transport": spec.get("transport", "http")},
            ))

        env = spec.get("env")
        if isinstance(env, dict):
            rep.capabilities.extend(_env_capabilities(env, where))

    return rep


# ---------------------------------------------------------------------------
# Claude Code settings.json  (hooks + permissions)
# ---------------------------------------------------------------------------

def extract_settings(text: str, rel_path: str, family: str) -> CapabilityReport:
    rep = CapabilityReport(path=rel_path, family=family, parsed=False)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        rep.parse_error = f"not valid JSON: {exc}"
        return rep
    rep.parsed = True
    if not isinstance(data, dict):
        rep.parse_error = "settings root is not an object"
        return rep

    # Hooks: every hook of type "command" runs a shell command on an event.
    hooks = data.get("hooks")
    if isinstance(hooks, dict):
        for event, matchers in hooks.items():
            if not isinstance(matchers, list):
                continue
            for m in matchers:
                if not isinstance(m, dict):
                    continue
                matcher = m.get("matcher", "*")
                for h in m.get("hooks", []) or []:
                    if not isinstance(h, dict):
                        continue
                    if h.get("type") == "command" and h.get("command"):
                        cmd = str(h["command"])
                        where = f"hook on {event} (matcher {matcher!r})"
                        rep.capabilities.append(Capability(
                            "process_exec",
                            f"{where} runs: {cmd}",
                            {"event": event, "matcher": matcher, "command": cmd},
                        ))
                        rep.capabilities.extend(_command_capabilities(cmd, where))

    # Permissions: allow/deny rules change what runs without asking.
    perms = data.get("permissions")
    if isinstance(perms, dict):
        for rule in perms.get("allow", []) or []:
            rep.capabilities.append(Capability(
                "permission_grant",
                f"allows without prompting: {rule}",
                {"effect": "allow", "rule": str(rule)},
            ))
        for rule in perms.get("deny", []) or []:
            rep.capabilities.append(Capability(
                "permission_grant",
                f"denies: {rule}",
                {"effect": "deny", "rule": str(rule)},
            ))
    return rep


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def extract_skill(skill_dir: Path, rel_path: str, family: str = "skill") -> CapabilityReport:
    """A skill/plugin is a directory. Its executing capability is any
    executable file it bundles beside SKILL.md — a script the agent can be
    told to run. We surface the fact; we do not read the script's intent."""
    rep = CapabilityReport(path=rel_path, family=family, parsed=True)
    if not skill_dir.is_dir():
        rep.parsed = False
        rep.parse_error = "skill path is not a directory"
        return rep
    for f in sorted(skill_dir.rglob("*")):
        if not f.is_file() or f.name == "SKILL.md":
            continue
        is_exec = f.suffix.lower() in _SCRIPT_EXT
        if not is_exec:
            try:
                if f.stat().st_mode & 0o111:
                    is_exec = True
                else:
                    with f.open("rb") as fh:
                        is_exec = fh.read(2) == b"#!"
            except OSError:
                is_exec = False
        if is_exec:
            rel = f.relative_to(skill_dir).as_posix()
            rep.capabilities.append(Capability(
                "bundled_script",
                f"skill bundles an executable script: {rel}",
                {"script": rel},
            ))
    return rep


def extract(path: Path, rel_path: str, family: str) -> CapabilityReport:
    """Extract capabilities from one discovered config file, by family."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return CapabilityReport(path=rel_path, family=family, parsed=False,
                                parse_error=f"unreadable: {exc}")

    if family in MCP_FAMILIES:
        return extract_mcp(text, rel_path, family)
    if family in SETTINGS_FAMILIES:
        return extract_settings(text, rel_path, family)
    # Skills/plugins are a directory with a bundled script; handled by the
    # caller walking the skill dir. A bare manifest yields no exec capability.
    return CapabilityReport(path=rel_path, family=family, parsed=True)
