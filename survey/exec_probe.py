"""Execution-config detection for the ecosystem sweep — the executing analog of
survey_probe.instruction_paths_in.

Where the instruction survey asks "what does the agent read and obey", this asks
"what does the agent LOAD AND RUN": MCP servers (.mcp.json, .cursor/mcp.json,
.gemini/settings.json), lifecycle hooks (.claude/settings.json), and skills
(.claude/skills/**/SKILL.md). For each it records origin (first-party vs
vendored vs installed-dependency) and the declared capabilities that make the
config dangerous — process execution, network egress, credential references,
floating versions, bundled scripts, permission grants.

Kept deliberately parallel to survey_probe so the two surveys report on the same
footing and reuse the same CODEOWNERS matcher (coverage_for, imported by the
crawler, not here).
"""

from __future__ import annotations

import json

# --- what counts as an executing config file -------------------------------
# kind -> auto-executing? MCP servers spawn and hooks run at trust time
# (auto); a skill is discoverable but model-invoked, so it is reported
# separately and never inflates the auto-executing headline.
AUTO_EXEC_KINDS = {"mcp", "hooks"}

_INSTALLED_MARKERS = ("node_modules", "site-packages", "bower_components",
                      "go/pkg/mod", ".venv", "venv", ".yarn/unplugged")
_VENDORED_MARKERS = ("vendor", "vendored", "third_party", "third-party",
                     "external", "deps", "Pods")

_SECRET_HINT = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL",
                "CRED", "AUTH", "APIKEY", "API_KEY", "ACCESS", "PRIVATE")


def classify_config(path: str) -> str | None:
    """The executing-config kind for a tree path, or None."""
    base = path.rsplit("/", 1)[-1]
    low = "/" + path
    if base == ".mcp.json":
        return "mcp"
    if base == "mcp.json" and "/.cursor/" in low:
        return "mcp"
    if path.endswith(".gemini/settings.json"):
        return "mcp"
    if path.endswith(".claude/settings.json") or path.endswith(".claude/settings.local.json"):
        return "hooks"
    if base == "SKILL.md" and ("/.claude/skills/" in low or low.startswith("/.claude/skills/")
                               or "/skills/" in low and "/.claude/" in low):
        return "skill"
    return None


def exec_origin(path: str) -> str:
    """Path-based provenance class, matching Ovrin's origin vocabulary.
    (Submodule detection needs .gitmodules and is left to the scanner; the
    survey classifies by path, which is conservative — it can only under-count
    third-party, never over-count it.)"""
    parts = path.split("/")
    joined = "/" + path
    if any(m in parts for m in _INSTALLED_MARKERS) or "go/pkg/mod" in joined:
        return "installed-dependency"
    if any(m in parts for m in _VENDORED_MARKERS):
        return "vendored"
    return "first-party"


def exec_configs_in(tree_paths: list[str]) -> list[dict]:
    """Every executing-config file in a repo tree, tagged with kind and origin.
    Skills also carry whether a bundled script sits next to them in the tree."""
    pathset = tree_paths if isinstance(tree_paths, set) else set(tree_paths)
    out = []
    for path in tree_paths:
        kind = classify_config(path)
        if not kind:
            continue
        rec = {"path": path, "kind": kind, "origin": exec_origin(path),
               "autoExec": kind in AUTO_EXEC_KINDS}
        if kind == "skill":
            skill_dir = path.rsplit("/", 1)[0]
            rec["bundledScript"] = any(
                p != path and p.startswith(skill_dir + "/")
                and p.rsplit(".", 1)[-1] in ("sh", "py", "js", "ts", "rb", "ps1", "bat")
                for p in pathset)
        out.append(rec)
    return out


# --- capability extraction from the config file's bytes --------------------

def _looks_secret(name: str) -> bool:
    u = str(name).upper()
    return any(h in u for h in _SECRET_HINT)


def _floating(arg: str) -> bool:
    a = str(arg)
    return a.endswith("@latest") or a.endswith("@*") or "@^" in a or "@~" in a


def caps_from_mcp(text: str) -> set[str]:
    caps: set[str] = set()
    try:
        spec = json.loads(text)
    except (ValueError, TypeError):
        return caps
    if not isinstance(spec, dict):   # some .mcp.json files are a top-level array
        return caps
    servers = spec.get("mcpServers") or spec.get("mcp_servers") or {}
    if not isinstance(servers, dict):
        return caps
    for s in servers.values():
        if not isinstance(s, dict):
            continue
        cmd = s.get("command")
        if cmd:
            caps.add("process_exec")
            c = str(cmd)
            if c.startswith("./") or c.startswith("../") or "node_modules" in c \
               or c.startswith("vendor") or "/" in c and not c.startswith("/usr"):
                caps.add("bundled_script")
        blob = json.dumps(s)
        if s.get("url") or s.get("httpUrl") or "http://" in blob or "https://" in blob:
            caps.add("network_egress")
        env = s.get("env") or {}
        if isinstance(env, dict) and any(_looks_secret(k) or _looks_secret(v) for k, v in env.items()):
            caps.add("credential_ref")
        for a in (s.get("args") or []):
            if _floating(a):
                caps.add("floating_version")
    return caps


def caps_from_hooks(text: str) -> set[str]:
    caps: set[str] = set()
    try:
        spec = json.loads(text)
    except (ValueError, TypeError):
        return caps
    if not isinstance(spec, dict):
        return caps
    if spec.get("hooks"):
        caps.add("process_exec")
        if "command" in json.dumps(spec.get("hooks")):
            caps.add("bundled_script")
    perms = spec.get("permissions")
    if isinstance(perms, dict):
        caps.add("permission_grant")
    if isinstance(spec.get("env"), dict):
        caps.add("env_read")
    return caps


def caps_for(kind: str, text: str | None) -> list[str]:
    if not text:
        return []
    if kind == "mcp":
        return sorted(caps_from_mcp(text))
    if kind == "hooks":
        return sorted(caps_from_hooks(text))
    return []
