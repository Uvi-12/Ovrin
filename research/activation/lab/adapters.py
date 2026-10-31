"""Agent adapters. Each adapter runs one coding-agent harness in a working
directory on a prompt, non-interactively, accepting workspace trust. Adapters
are built from `config.yaml` so the exact invocation (and the trust-accepting
flags, which differ by agent and version) lives in config, not code.

Three kinds:
  cli     - a real coding-agent CLI (claude, codex, gemini). cmd template.
  ollama  - an open-source harness driven by an Ollama-served model
            (llama / qwen / glm / ...). cmd template + model.
  mock    - no real agent; simulates a harness that loads config per a policy,
            spawning the canary commands it "loads". For self-testing the lab.

On an auth / quota / rate-limit failure an adapter raises TokenExpired, which
the orchestrator treats as a clean pause: state is already checkpointed, so the
next run resumes exactly where this one stopped.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Signatures of "your credentials/limits are the problem, not the task."
_TOKEN_RE = re.compile(
    r"(401|403|429|unauthoriz|invalid[ _-]?api|invalid[ _-]?key|api[ _-]?key|"
    r"quota|rate[ _-]?limit|exceeded|insufficient|billing|credit|"
    r"expired|authentication|permission denied by provider)",
    re.IGNORECASE,
)


class TokenExpired(Exception):
    """Raised when an adapter fails for auth/quota reasons. The orchestrator
    pauses and the next run resumes."""


@dataclass
class RunResult:
    returncode: int
    out: str
    err: str
    error: str | None = None  # "timeout" etc.


class Adapter:
    kind = "base"

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg

    def available(self) -> bool:
        raise NotImplementedError

    def run(self, workdir: Path, prompt: str, timeout: int) -> RunResult:
        raise NotImplementedError

    # Shared: run an argv template, substitute {PROMPT}/{MODEL}, map auth → TokenExpired.
    def _exec(self, cmd: list[str], workdir: Path, prompt: str, timeout: int) -> RunResult:
        model = self.cfg.get("model", "")
        root = self.cfg.get("_root", "")  # lab root, for {ROOT}/harness/... paths
        argv = [tok.replace("{PROMPT}", prompt).replace("{MODEL}", model)
                   .replace("{ROOT}", root) for tok in cmd]
        if any("<FILL>" in tok for tok in argv):
            raise SystemExit(
                f"adapter '{self.name}': the cmd in config.yaml still contains <FILL> — "
                f"set the real headless, trust-accepting invocation.")
        try:
            p = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return RunResult(-1, "", "", error="timeout")
        except FileNotFoundError:
            raise SystemExit(f"adapter '{self.name}': command not found: {argv[0]!r}")
        blob = (p.stdout or "") + "\n" + (p.stderr or "")
        if p.returncode != 0 and _TOKEN_RE.search(blob):
            raise TokenExpired(f"{self.name}: {blob.strip()[:200]}")
        return RunResult(p.returncode, p.stdout or "", p.stderr or "")


class CliAdapter(Adapter):
    kind = "cli"

    def available(self) -> bool:
        return shutil.which(self.cfg["cmd"][0]) is not None

    def run(self, workdir: Path, prompt: str, timeout: int) -> RunResult:
        return self._exec(self.cfg["cmd"], workdir, prompt, timeout)


class OllamaAdapter(Adapter):
    kind = "ollama"

    def available(self) -> bool:
        if shutil.which("ollama") is None:
            return False
        return shutil.which(self.cfg["harness_cmd"][0]) is not None

    def run(self, workdir: Path, prompt: str, timeout: int) -> RunResult:
        return self._exec(self.cfg["harness_cmd"], workdir, prompt, timeout)


class MockAdapter(Adapter):
    """Simulates a harness: loads config artifacts per a policy and spawns the
    canary commands it 'loads'. Exercises the whole detection path so the lab
    self-tests without any real agent. Not a result — a plumbing check."""
    kind = "mock"

    def available(self) -> bool:
        return True

    def run(self, workdir: Path, prompt: str, timeout: int) -> RunResult:
        loads = set(self.cfg.get("loads", ["root"]))
        # .mcp.json servers
        for p in sorted(workdir.rglob(".mcp.json")):
            origin = "root" if p.relative_to(workdir).as_posix() == ".mcp.json" else "vendored"
            if origin not in loads:
                continue
            self._spawn_mcp(p, workdir)
        # hooks + skills via settings/skill scripts
        if "root" in loads or "vendored" in loads:
            for p in sorted(workdir.rglob("settings.json")):
                if ".claude" in p.parts:
                    self._spawn_hooks(p, workdir, loads)
            for p in sorted(workdir.rglob("SKILL.md")):
                self._spawn_skill(p, workdir, loads)
        return RunResult(0, "mock-ran", "")

    def _spawn_mcp(self, path: Path, workdir: Path) -> None:
        try:
            spec = json.loads(path.read_text("utf-8"))
        except (ValueError, OSError):
            return
        for srv in (spec.get("mcpServers") or {}).values():
            cmd = [srv.get("command", "")] + [str(a) for a in srv.get("args", [])]
            if cmd[0]:
                subprocess.run(cmd, cwd=workdir, capture_output=True, timeout=10)

    def _spawn_hooks(self, path: Path, workdir: Path, loads: set) -> None:
        origin = "vendored" if any(m in path.parts for m in ("vendor", "node_modules")) else "root"
        if origin not in loads:
            return
        try:
            spec = json.loads(path.read_text("utf-8"))
        except (ValueError, OSError):
            return
        for matchers in (spec.get("hooks") or {}).values():
            for m in matchers if isinstance(matchers, list) else []:
                for h in (m.get("hooks") or []):
                    if h.get("type") == "command" and h.get("command"):
                        subprocess.run(h["command"], cwd=workdir, shell=True,
                                       capture_output=True, timeout=10)

    def _spawn_skill(self, path: Path, workdir: Path, loads: set) -> None:
        origin = "vendored" if any(m in path.parts for m in
                                   ("vendor", "node_modules", "plugins")) else "root"
        if origin not in loads:
            return
        for f in sorted(path.parent.rglob("*.sh")):
            subprocess.run(["sh", str(f)], cwd=workdir, capture_output=True, timeout=10)


_KINDS = {"cli": CliAdapter, "ollama": OllamaAdapter, "mock": MockAdapter}


def build(name: str, cfg: dict) -> Adapter:
    kind = cfg.get("type", "cli")
    if kind not in _KINDS:
        raise SystemExit(f"agent '{name}': unknown type {kind!r} (cli|ollama|mock)")
    return _KINDS[kind](name, cfg)
