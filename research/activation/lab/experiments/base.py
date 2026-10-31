"""Experiment interface and the shared run context."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..adapters import Adapter
from ..state import Store


@dataclass
class Ctx:
    cfg: dict
    adapters: dict  # name -> Adapter (enabled + available only)
    store: Store
    lab_dir: Path           # holds canary.sh
    results_dir: Path
    tmp_root: Path
    n: int                  # default trials per cell
    timeout: int

    @property
    def canary(self) -> Path:
        return self.lab_dir / "canary.sh"

    def live_agents(self) -> dict[str, Adapter]:
        return self.adapters


@dataclass
class Cell:
    id: str
    n: int
    meta: dict = field(default_factory=dict)


class Experiment:
    name = "base"
    title = ""

    def plan(self, ctx: Ctx) -> list[Cell]:
        raise NotImplementedError

    def trial(self, ctx: Ctx, cell: Cell, i: int) -> dict:
        raise NotImplementedError

    def aggregate(self, ctx: Ctx) -> list[str]:
        """Return human-readable summary lines for the report."""
        return []
