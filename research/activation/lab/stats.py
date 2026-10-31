"""Binomial statistics. Wilson score interval, because it keeps coverage near
0 and 1 where our rates often sit (0/N and N/N are common)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Proportion:
    k: int
    n: int
    p: float
    lo: float
    hi: float

    def pct(self) -> str:
        if self.n == 0:
            return "  n/a  (0/0)"
        return f"{self.p * 100:5.1f}%  [{self.lo * 100:.1f}, {self.hi * 100:.1f}]  ({self.k}/{self.n})"


def wilson(k: int, n: int, z: float = 1.96) -> Proportion:
    if n == 0:
        return Proportion(0, 0, 0.0, 0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return Proportion(k, n, p, max(0.0, centre - half), min(1.0, centre + half))


def rate_over(records: list[dict], field: str) -> Proportion:
    """Wilson proportion of records where record[field] is truthy."""
    n = len(records)
    k = sum(1 for r in records if r.get(field))
    return wilson(k, n)
