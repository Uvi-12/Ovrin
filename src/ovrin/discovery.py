"""Walk a directory and find every instruction file, whatever agent it belongs
to. Discovery is deliberately agent-agnostic: we collect everything that looks
like an instruction file, then let harness.py decide who would load it. Merging
those two steps is what produces overclaims about inheritance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .constants import MAX_HASH_BYTES, SKIP_DIRS
from .formats import Format, match_format


@dataclass
class Found:
    rel_path: str
    abs_path: Path
    family: str
    activation: str
    digest: str | None       # None when we declined to hash. Never a partial hash.
    digest_status: str       # complete | oversize | unreadable
    bytes: int


def _hash(path: Path) -> tuple[str | None, int, str]:
    # A hash of part of a file is not that file's hash. Oversize files get a
    # null digest and an honest status instead of a misleading value.
    size = path.stat().st_size
    if size > MAX_HASH_BYTES:
        return None, size, "oversize"
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}", size, "complete"


def scan(root: Path, formats: list[Format], max_depth: int | None = None) -> list[Found]:
    root = root.resolve()
    out: dict[str, Found] = {}
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if max_depth is not None and rel.count("/") > max_depth:
            continue
        fmt = match_format(rel, formats)
        if fmt is None:
            continue
        try:
            digest, size, status = _hash(path)
        except OSError:
            digest, size, status = None, 0, "unreadable"
        out[rel] = Found(
            rel_path=rel, abs_path=path, family=fmt.family,
            activation=fmt.activation, digest=digest,
            digest_status=status, bytes=size,
        )
    return sorted(out.values(), key=lambda f: f.rel_path)
