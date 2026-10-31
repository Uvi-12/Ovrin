"""Load config.yaml, resolve paths, and build the enabled adapters."""

from __future__ import annotations

import sys
from pathlib import Path

from . import adapters as adp


def load(config_path: Path) -> tuple[dict, Path]:
    try:
        import yaml
    except ModuleNotFoundError:
        sys.exit("ovrin-lab needs PyYAML:  pip install pyyaml  (or run ./run.sh)")
    root = config_path.resolve().parent
    cfg = yaml.safe_load(config_path.read_text("utf-8")) or {}
    cfg.setdefault("run", {})
    cfg["run"].setdefault("trials", 20)
    cfg["run"].setdefault("timeout", 180)
    cfg["run"].setdefault("tmp_root", ".lab-tmp")
    cfg.setdefault("experiments", ["census", "activation", "consequence",
                                   "defense", "effective_authority"])
    cfg.setdefault("activation", {}).setdefault("variants", ["root", "vendored", "transitive"])
    cfg.setdefault("consequence", {}).setdefault("cases", ["secret-read", "ci-disable"])
    cfg.setdefault("defense", {}).setdefault("pairs", 40)
    cfg.setdefault("census", {}).setdefault("corpus", "corpus")
    cfg.setdefault("agents", {})
    # resolve paths relative to the project root
    corpus = Path(cfg["census"]["corpus"])
    cfg["census"]["corpus"] = str(corpus if corpus.is_absolute() else root / corpus)
    # expose the lab root to adapters so a cmd can reference {ROOT}/harness/...
    for acfg in cfg["agents"].values():
        if isinstance(acfg, dict):
            acfg.setdefault("_root", str(root))
    return cfg, root


def build_adapters(cfg: dict, verbose: bool = True) -> dict:
    out = {}
    for name, acfg in cfg.get("agents", {}).items():
        if not acfg.get("enabled", False):
            continue
        a = adp.build(name, acfg)
        if a.available():
            out[name] = a
        elif verbose:
            print(f"  ! agent '{name}' enabled but not available on PATH — skipped")
    return out
