"""Terminal progress. Plain stdout so it works over SSH, in tmux, and in CI
logs without a TTY. One line per cell that updates in place when attached to a
terminal, and a newline-per-update fallback when piped to a file."""

from __future__ import annotations

import sys
import time


class Progress:
    def __init__(self, label: str, total: int):
        self.label = label
        self.total = total
        self.n = 0
        self.start = time.time()
        self._tty = sys.stdout.isatty()

    def tick(self, note: str = "") -> None:
        self.n += 1
        self._draw(note)

    def _draw(self, note: str) -> None:
        pct = (self.n / self.total * 100) if self.total else 100.0
        elapsed = time.time() - self.start
        rate = self.n / elapsed if elapsed > 0 else 0.0
        bar_w = 24
        filled = int(bar_w * self.n / self.total) if self.total else bar_w
        bar = "#" * filled + "-" * (bar_w - filled)
        line = (f"  {self.label:<34} [{bar}] {self.n:>4}/{self.total:<4} "
                f"{pct:5.1f}%  {rate:4.1f}/s  {note}")
        if self._tty:
            sys.stdout.write("\r" + line)
            sys.stdout.flush()
        else:
            sys.stdout.write(line + "\n")

    def done(self, summary: str) -> None:
        if self._tty:
            sys.stdout.write("\r" + " " * 110 + "\r")
        print(f"  {self.label:<34} {summary}")
