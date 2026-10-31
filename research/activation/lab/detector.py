"""Ovrin's static pre-run gate, lab edition: given a repo, predict which
executing config a harness would load that is third-party and unreviewed, and
what it can do. This is the DEFENSE under test, and the PREDICTOR we reconcile
against observed activation."""

from __future__ import annotations

from pathlib import Path

from . import capabilities as cap

VENDOR_MARKERS = ("vendor/", "node_modules/", "third_party/", "vendored/")
PLUGIN_MARKERS = (".claude/plugins/",)
COVERED_PREFIXES = (".mcp.json", ".claude/", ".github/")
EXEC_KINDS = {"process_exec", "network_egress", "credential_ref", "bundled_script"}


def origin_of(rel: str) -> str:
    if any(m in rel for m in PLUGIN_MARKERS):
        return "installed-dependency"
    if any(m in rel for m in VENDOR_MARKERS):
        return "vendored"
    return "repo"


def load_codeowners(repo: Path) -> list[str] | None:
    for cand in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        p = repo / cand
        if p.is_file():
            pats = []
            for line in p.read_text("utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    pats.append(line.split()[0])
            return pats
    return None


def _covered(rel: str, pats: list[str] | None) -> bool:
    if not pats:
        return False
    for pat in pats:
        if pat == "*":
            return True
        pp = pat.strip("/")
        if rel == pp or rel.startswith(pp + "/") or rel.startswith(pp):
            return True
    return False


def review_enforced(rel: str, origin: str, pats: list[str] | None) -> bool:
    # A path glob can MATCH vendored/installed content, but that was never
    # authored in a reviewed PR. Review is enforced only for first-party.
    return origin == "repo" and _covered(rel, pats)


def surface(repo: Path):
    for p in sorted(repo.rglob("*")):
        if not p.is_file():
            continue
        if p.name == ".mcp.json":
            rel = p.relative_to(repo).as_posix()
            yield rel, cap.extract(p, rel, "mcp")
        elif p.name == "settings.json" and ".claude" in p.parts:
            rel = p.relative_to(repo).as_posix()
            yield rel, cap.extract(p, rel, "claude-settings")
        elif p.name == "SKILL.md":
            d = p.parent
            rel = d.relative_to(repo).as_posix()
            yield rel, cap.extract_skill(d, rel, "skill")


def findings(repo: Path) -> list[dict]:
    pats = load_codeowners(repo)
    out = []
    for rel, rep in surface(repo):
        origin = origin_of(rel)
        exec_caps = sorted(rep.kinds & EXEC_KINDS)
        blocked = (origin != "repo"
                   and not review_enforced(rel, origin, pats)
                   and bool(exec_caps))
        out.append({"path": rel, "origin": origin, "exec": exec_caps,
                    "review_enforced": review_enforced(rel, origin, pats),
                    "blocked": blocked})
    return out


def predicts_block(repo: Path) -> bool:
    return any(f["blocked"] for f in findings(repo))
