"""Final report + coordinated-disclosure drafts.

Writes results/report.md (every experiment's summary) and, for each agent that
showed activation or a consequence, a results/disclosure/<agent>.md draft — so
findings go to vendors before they go to a stage."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import __version__
from . import fixtures
from .experiments import ORDER, REGISTRY
from .stats import rate_over


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def write_report(ctx, selected: list[str]) -> Path:
    lines = [f"# Ovrin Lab report", f"", f"- generated: {_now()}",
             f"- lab version: {__version__}", f"- trials/cell: {ctx.n}", ""]
    from . import provenance
    m = provenance.read(ctx.results_dir)
    if m:
        lines += ["## Environment (reproducibility manifest)", "",
                  f"- host: `{m.get('os')}`  ·  python {m.get('python')}",
                  f"- corpus sha256: `{m.get('corpus_sha256_12')}`  ·  "
                  f"variants: {', '.join(m.get('activation_variants') or [])}", ""]
        for name, a in (m.get("agents") or {}).items():
            v = a.get("version", a.get("kind"))
            lines.append(f"  - `{name}`: {v}")
        lines.append("")
    for name in ORDER:
        if name not in selected:
            continue
        exp = REGISTRY[name]()
        lines.append(f"## {exp.title}")
        lines.extend(exp.aggregate(ctx))
        lines.append("")
    out = ctx.results_dir / "report.md"
    out.write_text("\n".join(lines), "utf-8")
    return out


def write_disclosures(ctx) -> list[Path]:
    act = ctx.store.read_records("activation")
    cons = ctx.store.read_records("consequence")
    agents = sorted({r["agent"] for r in act} | {r["agent"] for r in cons})
    ddir = ctx.results_dir / "disclosure"
    written = []
    for agent in agents:
        a_v = [r for r in act if r["agent"] == agent and r.get("variant") in fixtures.THIRD_PARTY_VARIANTS]
        c_v = [r for r in cons if r["agent"] == agent]
        act_rate = rate_over(a_v, "activated")
        if act_rate.k == 0 and not any(r.get("consequence") for r in c_v):
            continue  # nothing to disclose for this agent
        body = _disclosure_md(agent, act_rate, c_v)
        p = ddir / f"{agent}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, "utf-8")
        written.append(p)
    return written


def _disclosure_md(agent: str, act_rate, cons_recs: list[dict]) -> str:
    cons_lines = []
    for case in sorted({r["case"] for r in cons_recs}):
        sub = [r for r in cons_recs if r["case"] == case]
        cons_lines.append(f"  - `{case}`: {rate_over(sub, 'consequence').pct()}")
    cons_block = "\n".join(cons_lines) or "  - (none fired)"
    return f"""# Coordinated disclosure draft — {agent}

_Generated {_now()} by Ovrin Lab. Draft for the vendor; review before sending._

## Summary
In controlled, benign-canary testing, `{agent}` executed **third-party, unreviewed
agent configuration** on a single workspace-trust accept while running a neutral
task — either a server definition carried inside a dependency (never present at
the reviewed repository root), or a root config whose server command executed
code vendored under a dependency. Neither path required a separate approval.

- Vendored/transitive activation under trust: **{act_rate.pct()}**
- Security-shaped consequences (inert canary):
{cons_block}

## Why it matters
The workspace-trust boundary does not distinguish first-party configuration
from configuration carried in by a dependency. A package a developer never read
can place a `.mcp.json` the agent will spawn, with no separate approval.

## Reproduction
Fixtures and a runnable harness are included in the Ovrin Lab release
(`research/agent-surface/activation/` and `lab/`). All payloads are inert
canaries (a marker file; a toy secret; a sentinel line in a toy workflow). No
real credentials, exfiltration, or code execution against third-party systems.

## Requested
Confirmation of the behavior and intended handling, and a reasonable disclosure
window before publication. Happy to share full per-trial logs.

## Scope / ethics
Testing was performed only against our own throwaway repositories with inert
canaries. See ETHICS.md.
"""
