"""A1 / A2 — ecosystem census. Static, no agent. Prevalence of the executing
config surface, how much is third-party carried, how much escapes review, and
what capability it declares, across a corpus of repos."""

from __future__ import annotations

from pathlib import Path

from .. import detector as det
from ..stats import wilson
from .base import Cell, Ctx, Experiment


class Census(Experiment):
    name = "census"
    title = "A1/A2 — agent-config census (static)"

    def plan(self, ctx: Ctx) -> list[Cell]:
        return [Cell("corpus", 1, {})]

    def trial(self, ctx: Ctx, cell: Cell, i: int) -> dict:
        corpus = Path(ctx.cfg["census"]["corpus"])
        repos = [d for d in sorted(corpus.iterdir()) if d.is_dir()] if corpus.is_dir() else []
        n = len(repos)
        has_exec = has_tp_exec = has_ungov = 0
        caps: dict[str, int] = {}
        for repo in repos:
            exec_here = tp_exec = ungov = False
            pats = det.load_codeowners(repo)
            for rel, rep in det.surface(repo):
                for k in rep.kinds:
                    caps[k] = caps.get(k, 0) + 1
                ex = rep.kinds & det.EXEC_KINDS
                if ex:
                    exec_here = True
                    origin = det.origin_of(rel)
                    if origin != "repo":
                        tp_exec = True
                        if not det.review_enforced(rel, origin, pats):
                            ungov = True
            has_exec += exec_here
            has_tp_exec += tp_exec
            has_ungov += ungov
        return {"experiment": self.name, "cell": cell.id, "trial": i, "repos": n,
                "executing": has_exec, "thirdparty_exec": has_tp_exec,
                "ungoverned_exec": has_ungov, "capabilities": caps}

    def aggregate(self, ctx: Ctx) -> list[str]:
        recs = ctx.store.read_records(self.name)
        if not recs:
            return ["  (no corpus scanned)"]
        r = recs[-1]
        n = r["repos"]
        out = [f"  corpus: {n} repos"]
        out.append(f"  executing surface present   {wilson(r['executing'], n).pct()}")
        out.append(f"  third-party executing       {wilson(r['thirdparty_exec'], n).pct()}")
        out.append(f"  UNGOVERNED executing        {wilson(r['ungoverned_exec'], n).pct()}   <- headline")
        if r.get("capabilities"):
            caps = ", ".join(f"{k}:{v}" for k, v in sorted(r["capabilities"].items(), key=lambda kv: -kv[1]))
            out.append(f"  declared capability (artifacts): {caps}")
        return out
