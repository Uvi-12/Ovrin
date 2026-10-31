"""Checkpointing and resume.

Every trial is keyed `<experiment>/<cell>/<trial>`. Completed keys live in
`state.json`; each trial's record is appended to `<experiment>.jsonl`. A run
loads the state, skips completed trials, and continues. So a run interrupted
by an expired token resumes exactly where it stopped the next time it starts —
nothing is re-run, nothing is lost.
"""

from __future__ import annotations

import json
from pathlib import Path


class Store:
    def __init__(self, results_dir: Path):
        self.dir = results_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        self._done: set[str] = set()
        if self.state_path.exists():
            try:
                self._done = set(json.loads(self.state_path.read_text("utf-8")).get("done", []))
            except (ValueError, OSError):
                self._done = set()
        self._handles: dict[str, object] = {}

    @staticmethod
    def key(experiment: str, cell: str, trial: int) -> str:
        return f"{experiment}/{cell}/{trial}"

    def is_done(self, experiment: str, cell: str, trial: int) -> bool:
        return self.key(experiment, cell, trial) in self._done

    def done_count(self, experiment: str, cell: str) -> int:
        prefix = f"{experiment}/{cell}/"
        return sum(1 for k in self._done if k.startswith(prefix))

    def record(self, experiment: str, cell: str, trial: int, rec: dict) -> None:
        fh = self._handles.get(experiment)
        if fh is None:
            fh = (self.dir / f"{experiment}.jsonl").open("a", encoding="utf-8")
            self._handles[experiment] = fh
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        self._done.add(self.key(experiment, cell, trial))
        self._flush_state()

    def _flush_state(self) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"done": sorted(self._done)}), encoding="utf-8")
        tmp.replace(self.state_path)

    def read_records(self, experiment: str) -> list[dict]:
        p = self.dir / f"{experiment}.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
        return out

    def close(self) -> None:
        for fh in self._handles.values():
            try:
                fh.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        self._handles.clear()
