"""Which agents would load which files. The verdict is conservative on purpose:
where we have not verified a harness's behaviour, we say so rather than guess. An
unearned 'loaded' is the failure mode that would discredit the whole manifest."""
from __future__ import annotations
import fnmatch
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
import yaml
@dataclass
class Harness:
    id: str
    name: str
    open_source: bool
    reads: list[str]
    walks_tree: bool
    walks_ancestors: bool
    respects_ignore: object
    precedence: str
    confidence: str
    source: str
    note: str = ""
    max_doc_bytes: int | None = None
    case_insensitive: bool = False
    claims: dict = None  # per-behaviour {value, confidence}; set in load()
@dataclass
class Rules:
    version: str
    verified: str
    harnesses: list[Harness]
    vendor_markers: tuple[str, ...]
    @classmethod
    def load(cls, path: Path | None = None) -> Rules:
        if path is not None:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            text = resources.files("ovrin.data").joinpath("harnesses.yaml").read_text("utf-8")
            raw = yaml.safe_load(text)
        hs = []
        for h in raw.get("harnesses", []):
            hs.append(Harness(
                id=h["id"], name=h["name"], open_source=bool(h.get("open_source")),
                reads=list(h.get("reads", [])),
                walks_tree=bool(h.get("walks_tree")),
                walks_ancestors=bool(h.get("walks_ancestors")),
                respects_ignore=h.get("respects_ignore", "unknown"),
                precedence=h.get("precedence", "unknown"),
                confidence=h.get("confidence", "unknown"),
                source=h.get("source", ""), note=(h.get("note") or "").strip(),
                max_doc_bytes=h.get("max_doc_bytes"),
                case_insensitive=bool(h.get("case_insensitive")),
                claims=h.get("claims", {}),
            ))
        return cls(str(raw.get("version", "0")), str(raw.get("verified", "")),
                   hs, tuple(raw.get("vendor_markers", [])))
def reads_name(h: Harness, rel: str) -> bool:
    name = Path(rel).name
    for pat in h.reads:
        if "/" in pat:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, f"**/{pat}"):
                return True
        else:
            a, b = (name.lower(), pat.lower()) if h.case_insensitive else (name, pat)
            if a == b:
                return True
    return False
def _on_root_to_cwd_chain(rel: str, active_path: str) -> bool:
    """True if the instruction file's directory lies on the chain from the
    repository root down to active_path. A root-to-cwd harness (e.g. Codex)
    only loads files whose directory is an ancestor of, or equal to, the
    working directory it was launched in."""
    file_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
    active = active_path.strip("/")
    if file_dir == "":
        return True
    active_segs = active.split("/") if active else []
    file_segs = file_dir.split("/")
    if len(file_segs) > len(active_segs):
        return False
    return active_segs[:len(file_segs)] == file_segs
def reachability(h: Harness, rel: str, *, is_ignored: bool, origin_cls: str,
                 active_path: str | None = None) -> tuple[str, str]:
    """Return (verdict, reason) for one harness and one file.

    active_path is the working directory the agent is launched in, relative to
    the repository root. When given, a root-to-cwd harness only loads a nested
    file if that file lies on the root->active_path chain; a file elsewhere in
    the tree is 'not-discovered' even though the harness walks trees. When
    active_path is None the location is unconstrained (the scanner's default),
    so the answer is 'could this file ever be loaded from some working
    directory', not 'is it loaded from a specific one'."""
    if not reads_name(h, rel):
        return "not-discovered", "harness does not read this filename"
    depth = rel.count("/")
    if depth > 0 and not h.walks_tree:
        return "not-discovered", "harness reads root-level configuration only"
    if active_path is not None and depth > 0 and h.walks_ancestors:
        if not _on_root_to_cwd_chain(rel, active_path):
            return ("not-discovered",
                    f"file is not on the root-to-cwd chain for working dir '{active_path}'")
    if is_ignored:
        if h.respects_ignore in (True, "documented", "observed"):
            return "ignored", "path is git-ignored and this harness respects ignore rules"
        if h.respects_ignore is False:
            return "loaded", "path is git-ignored but this harness does not respect ignore rules"
        return "unverified", "path is git-ignored; harness ignore behaviour not verified"
    third_party = {"vendored", "submodule", "installed-dependency"}
    if origin_cls in third_party and h.confidence == "unknown":
        return "unverified", "third-party path and harness behaviour not verified"
    return "loaded", "within this harness's discovery scope"
