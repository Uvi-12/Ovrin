"""Executing configuration: MCP servers, hooks, and skills."""

import json
import subprocess
from pathlib import Path

import pytest

from ovrin import execconfig
from ovrin.cli import main
from ovrin.manifest import build
from ovrin.spdx import to_spdx


def _git(r: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)


def _write(r: Path, rel: str, text: str) -> None:
    p = r / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


HOOK = lambda cmd: json.dumps({"hooks": {"SessionStart": [  # noqa: E731
    {"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}]}})


@pytest.fixture
def exec_repo(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    r.mkdir()
    _write(r, ".mcp.json", json.dumps({"mcpServers": {"docs": {
        "command": "npx", "args": ["-y", "@acme/docs-mcp@1.4.2"]}}}))
    _write(r, ".claude/settings.json", HOOK("bash vendor/kit/setup.sh"))
    _write(r, "vendor/kit/setup.sh", "#!/bin/sh\necho canary\n")
    _write(r, "vendor/kit/.mcp.json", json.dumps({"mcpServers": {"t": {
        "command": "node", "args": ["server.js"]}}}))
    _write(r, ".github/CODEOWNERS", "*  @org/maintainers\n")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "a@b.c")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r


def _entry(m, path):
    return next(e for e in m["executing"] if e["path"] == path)


# --- matching -------------------------------------------------------------

@pytest.mark.parametrize("rel,kind,launch", [
    (".mcp.json", "mcp", ""),
    ("vendor/kit/.mcp.json", "mcp", "vendor/kit"),
    (".cursor/mcp.json", "cursor-mcp", ""),
    (".gemini/settings.json", "gemini-settings", ""),
    (".claude/settings.json", "claude-settings", ""),
    (".claude/settings.local.json", "claude-settings-local", ""),
    (".claude/skills/deploy/SKILL.md", "skill", ""),
    ("node_modules/x/.claude/settings.json", "claude-settings", "node_modules/x"),
])
def test_match_kinds_and_launch_dir(rel, kind, launch):
    fmts = execconfig.load().formats
    fmt, d = execconfig.match(rel, fmts)
    assert (fmt.kind, d) == (kind, launch)


@pytest.mark.parametrize("rel", ["settings.json", "mcp.json", "docs/.claude/notes.md",
                                 ".claude/skills/SKILL.md", "src/app.py"])
def test_non_config_paths_do_not_match(rel):
    assert execconfig.match(rel, execconfig.load().formats) is None


def test_codex_is_reported_as_not_repo_local():
    cat = execconfig.load()
    assert any(n["harness"] == "codex-cli" for n in cat.not_repo_local)
    loaders = {ld["harness"] for f in cat.formats for ld in f.loaders}
    assert "codex-cli" not in loaders


# --- capability extraction ------------------------------------------------

def test_mcp_capabilities(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text(json.dumps({"mcpServers": {
        "a": {"command": "npx", "args": ["-y", "pkg@latest"], "env": {"GITHUB_TOKEN": "x"}},
        "b": {"url": "https://mcp.example.com/sse"}}}))
    fmt, _ = execconfig.match(".mcp.json", execconfig.load().formats)
    kinds = {c.kind for c in execconfig.extract(p, ".mcp.json", fmt).capabilities}
    assert {"process_exec", "floating_version", "credential_ref", "network_egress"} <= kinds


def test_gemini_settings_httpurl_and_no_servers(tmp_path):
    fmt, _ = execconfig.match(".gemini/settings.json", execconfig.load().formats)
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"mcpServers": {"r": {"httpUrl": "https://x.example/mcp"}}}))
    assert {c.kind for c in execconfig.extract(p, "s", fmt).capabilities} == {"network_egress"}
    p.write_text(json.dumps({"theme": "dark"}))
    rep = execconfig.extract(p, "s", fmt)
    assert rep.capabilities == [] and rep.parsed and rep.parse_error is None


def test_malformed_json_is_reported_not_raised(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text("{ not json")
    fmt, _ = execconfig.match(".mcp.json", execconfig.load().formats)
    rep = execconfig.extract(p, ".mcp.json", fmt)
    assert rep.parsed is False and "JSON" in rep.parse_error


def test_top_level_array_mcp_does_not_crash(tmp_path):
    p = tmp_path / ".mcp.json"
    p.write_text("[1, 2]")
    fmt, _ = execconfig.match(".mcp.json", execconfig.load().formats)
    assert execconfig.extract(p, ".mcp.json", fmt).capabilities == []


def test_settings_hooks_and_permissions(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({**json.loads(HOOK("./scripts/x.sh")),
                             "permissions": {"allow": ["Bash(*)"]}}))
    fmt, _ = execconfig.match(".claude/settings.json", execconfig.load().formats)
    kinds = {c.kind for c in execconfig.extract(p, ".claude/settings.json", fmt).capabilities}
    assert {"process_exec", "permission_grant"} <= kinds


# --- code paths a command runs --------------------------------------------

def _report_for(cmd: str, rel=".claude/settings.json"):
    from ovrin import capabilities as caps
    return caps.extract_settings(HOOK(cmd), rel, "settings")


@pytest.mark.parametrize("cmd,launch,expected", [
    ("bash vendor/kit/setup.sh", "", ["vendor/kit/setup.sh"]),
    ('"$CLAUDE_PROJECT_DIR"/node_modules/.bin/x', "", ["node_modules/.bin/x"]),
    ("${CLAUDE_PROJECT_DIR}/scripts/a.sh", "", ["scripts/a.sh"]),
    ("npx -y @scope/pkg@1.0.0", "", []),
    ("bash ../outside.sh", "", []),
    ("bash /usr/local/bin/x", "", []),
    ("node lib/server.js", "vendor/kit", ["vendor/kit/lib/server.js"]),
])
def test_code_paths(cmd, launch, expected):
    assert execconfig.code_paths(_report_for(cmd), launch) == expected


# --- the manifest and the gate --------------------------------------------

def test_no_exec_config_in_instruction_only_repo(repo):
    m = build(repo, no_timestamp=True)
    assert m["executing"] == []
    assert m["summary"]["executing"]["blocked"] == 0


def test_root_hook_running_vendored_code_is_blocked(exec_repo):
    m = build(exec_repo, no_timestamp=True)
    e = _entry(m, ".claude/settings.json")
    assert e["loadedBy"]["claude-code"]["verdict"] == "loaded"
    assert e["runsThirdPartyCode"][0]["path"] == "vendor/kit/setup.sh"
    assert e["runsThirdPartyCode"][0]["origin"] == "vendored"
    assert e["risk"]["blocked"]
    assert {r["code"] for r in e["risk"]["reasons"]} == {"third-party-code"}


def test_pinned_first_party_mcp_with_codeowners_is_not_blocked(exec_repo):
    e = _entry(build(exec_repo, no_timestamp=True), ".mcp.json")
    assert e["origin"]["class"] == "repo"
    assert e["review"]["enforceable"] is None
    assert not e["risk"]["blocked"] and e["risk"]["reasons"] == []


def test_buried_vendored_mcp_is_not_loaded_only_warned(exec_repo):
    e = _entry(build(exec_repo, no_timestamp=True), "vendor/kit/.mcp.json")
    assert e["origin"]["class"] == "vendored"
    assert e["launchDir"] == "vendor/kit"
    assert all(r["verdict"] == "not-discovered" for r in e["loadedBy"].values())
    assert not e["risk"]["blocked"]
    assert [r["code"] for r in e["risk"]["reasons"]] == ["nested-third-party"]


def test_unreviewed_root_exec_is_blocked(tmp_path):
    r = tmp_path / "p"
    r.mkdir()
    server = {"command": "python", "args": ["s.py"]}
    _write(r, ".mcp.json", json.dumps({"mcpServers": {"s": server}}))
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "a@b.c")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "x")
    e = _entry(build(r, no_timestamp=True), ".mcp.json")
    assert e["review"]["enforceable"] is False      # no CODEOWNERS at all
    assert [x["code"] for x in e["risk"]["reasons"]] == ["unreviewed-exec"]


def test_gitignored_local_settings_hook_is_unreviewed(exec_repo):
    _write(exec_repo, ".gitignore", ".claude/settings.local.json\n")
    _write(exec_repo, ".claude/settings.local.json", HOOK("echo hi"))
    e = _entry(build(exec_repo, no_timestamp=True), ".claude/settings.local.json")
    assert e["gitIgnored"] and e["review"]["enforceable"] is False
    assert "unreviewed-exec" in {x["code"] for x in e["risk"]["reasons"]}


def test_skill_is_model_invoked_and_never_blocks(exec_repo):
    _write(exec_repo, ".claude/skills/deploy/SKILL.md", "---\nname: deploy\n---\n")
    _write(exec_repo, ".claude/skills/deploy/run.sh", "#!/bin/sh\necho canary\n")
    e = _entry(build(exec_repo, no_timestamp=True), ".claude/skills/deploy/SKILL.md")
    assert e["autoExec"] is False
    assert any(c["kind"] == "bundled_script" for c in e["capabilities"])
    assert not e["risk"]["blocked"]


def test_floating_version_warns(exec_repo):
    _write(exec_repo, ".mcp.json", json.dumps({"mcpServers": {"d": {
        "command": "npx", "args": ["-y", "@acme/docs-mcp@latest"]}}}))
    e = _entry(build(exec_repo, no_timestamp=True), ".mcp.json")
    assert "floating-version" in {x["code"] for x in e["risk"]["reasons"]}
    assert not e["risk"]["blocked"]


def test_summary_counts(exec_repo):
    s = build(exec_repo, no_timestamp=True)["summary"]["executing"]
    assert s["total"] == 3 and s["loadedAtRoot"] == 2
    assert s["runsThirdPartyCode"] == 1 and s["blocked"] == 1
    assert s["byCapability"]["process_exec"] == 3


def test_spdx_includes_executing_files(exec_repo):
    doc = to_spdx(build(exec_repo, no_timestamp=True))
    names = {n.get("name") for n in doc["@graph"]}
    assert {".mcp.json", ".claude/settings.json"} <= names
    node = next(n for n in doc["@graph"] if n.get("name") == ".claude/settings.json")
    assert "runsThirdPartyCode=vendor/kit/setup.sh" in node["comment"]


# --- CLI ------------------------------------------------------------------

def test_cli_exec_gate_fails_and_explains(exec_repo, capsys):
    rc = main(["scan", str(exec_repo), "-f", "json", "--fail-on-exec-risk"])
    err = capsys.readouterr().err
    assert rc == 1 and "BLOCK .claude/settings.json" in err


def test_cli_exec_gate_passes_without_findings(repo):
    assert main(["scan", str(repo), "-f", "json", "--fail-on-exec-risk"]) == 0


def test_cli_table_shows_executing_section(exec_repo, capsys):
    main(["scan", str(exec_repo), "--no-color"])
    out = capsys.readouterr().out
    assert "Executing configuration" in out and "BLOCK" in out and "codex-cli" in out


def test_cli_harnesses_lists_exec_rules(capsys):
    main(["harnesses"])
    out = capsys.readouterr().out
    assert ".mcp.json" in out and "observed" in out and "codex-cli" in out


def test_cli_reports_every_failing_gate(exec_repo, capsys):
    _write(exec_repo, "vendor/kit/AGENTS.md", "canary\n")
    _git(exec_repo, "add", "-A")
    _git(exec_repo, "commit", "-qm", "vendored notes")
    rc = main(["scan", str(exec_repo), "-f", "json",
               "--fail-on-third-party", "--fail-on-exec-risk"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "THIRD-PARTY vendor/kit/AGENTS.md" in err and "BLOCK .claude/settings.json" in err
