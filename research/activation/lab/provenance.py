"""Reproducibility manifest: what ran, against which agent versions, where, and
when. A benchmark number is only as defensible as the environment captured with
it, so this is written once per results set (results/manifest.json) and echoed
into the report. On --fresh the results are wiped and the manifest is recaptured.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path


def _ver(cmd0: str) -> str:
    try:
        p = subprocess.run([cmd0, "--version"], capture_output=True, text=True, timeout=30)
        blob = (p.stdout or p.stderr or "").strip()
        return blob.splitlines()[0] if blob else "(no version output)"
    except Exception as e:  # noqa: BLE001
        return f"(unavailable: {e.__class__.__name__})"


def _corpus_hash(corpus: Path) -> str:
    h = hashlib.sha256()
    if corpus.is_dir():
        for f in sorted(p for p in corpus.rglob("*") if p.is_file()):
            h.update(f.relative_to(corpus).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def capture(cfg: dict, adapters: dict, trials: int) -> dict:
    agents = {}
    for name, ad in adapters.items():
        entry = {"kind": ad.kind}
        cmd = ad.cfg.get("cmd") or ad.cfg.get("harness_cmd")
        if cmd:
            entry["cmd"] = [t for t in cmd if t != "{PROMPT}"]
            entry["version"] = _ver(cmd[0])
        if ad.cfg.get("model"):
            entry["model"] = ad.cfg["model"]
        agents[name] = entry
    return {
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "trials_per_cell": trials,
        "experiments": cfg.get("experiments"),
        "activation_variants": cfg.get("activation", {}).get("variants"),
        "consequence_cases": cfg.get("consequence", {}).get("cases"),
        "corpus_sha256_12": _corpus_hash(Path(cfg["census"]["corpus"])),
        "agents": agents,
    }


def ensure(cfg: dict, adapters: dict, trials: int, results_dir: Path) -> Path:
    """Write results/manifest.json if absent; return its path either way."""
    results_dir.mkdir(parents=True, exist_ok=True)
    p = results_dir / "manifest.json"
    if not p.exists():
        p.write_text(json.dumps(capture(cfg, adapters, trials), indent=2), "utf-8")
    return p


def read(results_dir: Path) -> dict | None:
    p = results_dir / "manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (ValueError, OSError):
        return None
