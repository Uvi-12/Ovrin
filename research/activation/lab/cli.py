"""Orchestrator. Runs the selected experiments, checkpointing every trial, so
an interrupted run (expired token, Ctrl-C, crash) resumes exactly where it
stopped. Progress prints to the terminal."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from . import config as cfgmod
from . import provenance
from . import report
from .adapters import TokenExpired
from .experiments import ORDER, REGISTRY
from .experiments.base import Ctx
from .progress import Progress
from .state import Store


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ovrin-lab", description=__doc__)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--only", nargs="+", help="run only these experiments")
    ap.add_argument("--agents", nargs="+",
                    help="run only these enabled agents (for parallel, one per terminal)")
    ap.add_argument("--run-id",
                    help="write to results/<run-id>/ so parallel runs don't collide")
    ap.add_argument("--fresh", action="store_true", help="wipe this run's results and start over")
    ap.add_argument("--list-agents", action="store_true")
    a = ap.parse_args(argv)

    cfg, root = cfgmod.load(Path(a.config))
    print(f"Ovrin Lab {__version__}")
    adapters = cfgmod.build_adapters(cfg)
    if a.agents:
        missing = [x for x in a.agents if x not in adapters]
        if missing:
            print(f"  ! requested but not enabled+available: {', '.join(missing)}")
        adapters = {k: v for k, v in adapters.items() if k in a.agents}

    if a.list_agents:
        if not adapters:
            print("  no enabled+available agents (edit config.yaml → agents)")
        for name, ad in adapters.items():
            print(f"  {name:<18} {ad.kind}")
        return 0

    results = root / "results" / a.run_id if a.run_id else root / "results"
    if a.fresh and results.exists():
        shutil.rmtree(results)
    tmp_root = root / cfg["run"]["tmp_root"]
    tmp_root.mkdir(parents=True, exist_ok=True)
    store = Store(results)
    ctx = Ctx(cfg=cfg, adapters=adapters, store=store, lab_dir=root / "lab",
              results_dir=results, tmp_root=tmp_root,
              n=int(cfg["run"]["trials"]), timeout=int(cfg["run"]["timeout"]))

    mpath = provenance.ensure(cfg, adapters, ctx.n, results)

    selected = [e for e in ORDER if e in cfg["experiments"] and (not a.only or e in a.only)]
    print(f"agents: {', '.join(adapters) or '(none — static experiments only)'}")
    print(f"experiments: {', '.join(selected)}   trials/cell: {ctx.n}\n")

    for name in selected:
        exp = REGISTRY[name]()
        print(f"== {exp.title} ==")
        cells = exp.plan(ctx)
        if not cells:
            print("  (no cells — e.g. this experiment needs a live agent and none is enabled)\n")
            continue
        for cell in cells:
            done0 = store.done_count(name, cell.id)
            prog = Progress(cell.id, cell.n)
            prog.n = done0
            for i in range(cell.n):
                if store.is_done(name, cell.id, i):
                    continue
                try:
                    rec = exp.trial(ctx, cell, i)
                except TokenExpired as e:
                    print(f"\n\n[PAUSED] token/quota exhausted ({e}).")
                    print("Progress is checkpointed. Run ./resume.sh once your keys/credits")
                    print("are restored — it continues exactly where it stopped.")
                    store.close()
                    return 2
                except KeyboardInterrupt:
                    print("\n\n[PAUSED] interrupted. ./resume.sh to continue.")
                    store.close()
                    return 130
                store.record(name, cell.id, i, rec)
                prog.tick(note=cell.id)
            prog.done(f"{cell.n} trials")
        for line in exp.aggregate(ctx):
            print(line)
        print()

    rp = report.write_report(ctx, selected)
    dd = report.write_disclosures(ctx)
    store.close()
    print(f"report:   {rp}")
    print(f"manifest: {mpath}")
    if dd:
        print("disclosure drafts:")
        for p in dd:
            print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
