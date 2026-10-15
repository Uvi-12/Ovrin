"""Ovrin delegation — the D(s,c) primitive.

The paper defines Instruction Authority Divergence formally as:

    IAD_h(x, c)  <=>  A_h(x, c) = 1  AND  D(P(x), c) = 0

where:
    P(x) is the provenance (source) of instruction artifact x,
    D(s, c) is 1 iff source s has been explicitly delegated authority
             to govern execution context c under the project policy,
    A_h(x, c) is 1 iff harness h resolves x as authoritative in c.

Everything in the earlier `enforce.py` gate encodes an *approximation* of
D via heuristics (origin class + review coverage + reachability). This
module makes D a first-class, machine-readable, project-declared object,
so that a reviewer's question "why isn't your reference implementation
actually consulting D?" has a concrete answer.

Wire model
----------
A project ships an `authority-policy.yaml` file at the repository root
(or supplied via --policy). Each rule declares a delegation:

    version: 1
    delegations:
      - source: "pkg:npm/example-policy@1.4.2"
        harness: "claude-code"        # optional; omit for any harness
        context:
          paths: ["vendor/example/**"]
        authority:
          instruction: true

      - source: "pkg:npm/example-policy@1.4.2"
        context:
          paths: ["config/security/**"]
        authority:
          instruction: false

    default:
      instruction: false              # unknown source, unknown context => not delegated

Semantics
---------
D(s, c) returns 1 iff at least one delegation rule matches (s, c) and
that rule's `authority.instruction` is true, AND no negative rule matches
(s, c) with `authority.instruction` false. Negative rules take precedence.
If no rule matches, D(s, c) = `default.instruction`, which the paper
recommends setting to 0 (deny-by-default).

Sources are named with Package URL (purl) syntax where possible:
    pkg:npm/lodash@4.17.21
    pkg:cargo/tokio@1.0.0
    pkg:golang/github.com/pkg/errors@v0.9.1
For repository sources (first-party):
    repo:default  — the current repository's own files
    repo:workspace/<name> — a workspace subpackage
    repo:submodule/<path> — a submodule

Context is a path glob against the *target* the agent is working on
(cwd + task path). A rule with an empty `context` matches every context.

Why this is not just a policy file
----------------------------------
The scientific claim in the paper is that provenance and repository
governance are not, on their own, delegation. `authority-policy.yaml`
is what the project uses to *express* delegation, but the paper is
about the missing binding, not about a YAML syntax. Any project that
manages agent instructions today already has an implicit policy; this
module makes the implicit policy explicit and comparable to the
harness-resolved authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
try:
    from pathspec import PathSpec
    _HAS_PATHSPEC = True
except ImportError:
    _HAS_PATHSPEC = False


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DelegationRule:
    """One declared delegation. Deny-by-negation, deny-by-default."""
    source: str                        # purl or repo:* identifier
    context_paths: tuple[str, ...]     # path globs; empty tuple = any context
    harness: str | None                # None = any harness
    instruction_delegated: bool        # authority.instruction
    origin_line: int = 0               # for diagnostics


@dataclass(frozen=True)
class DelegationPolicy:
    """A parsed authority-policy.yaml."""
    version: int
    rules: tuple[DelegationRule, ...]
    default_instruction: bool          # default.instruction

    @property
    def rule_count(self) -> int:
        return len(self.rules)


@dataclass(frozen=True)
class DelegationVerdict:
    """Answer to D(s, c) for one (source, context, harness) query."""
    delegated: bool                    # the boolean D value; 1 if True else 0
    matched_rule: DelegationRule | None
    matched_by: str                    # "default" | "positive" | "negative"
    reason: str

    def as_int(self) -> int:
        return 1 if self.delegated else 0


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------

class PolicyError(ValueError):
    """Raised on malformed authority-policy.yaml."""


def load_policy(path: Path) -> DelegationPolicy:
    """Load and validate an authority-policy.yaml file."""
    if not path.is_file():
        raise PolicyError(f"policy file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PolicyError(f"policy YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise PolicyError("policy root must be a mapping")
    return _validate(raw)


def load_policy_from_string(text: str) -> DelegationPolicy:
    """Parse policy from an in-memory string. Used by tests."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise PolicyError(f"policy YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise PolicyError("policy root must be a mapping")
    return _validate(raw)


def _validate(raw: dict[str, Any]) -> DelegationPolicy:
    version = raw.get("version", 1)
    if not isinstance(version, int) or version != 1:
        raise PolicyError(f"unsupported policy version: {version!r}")

    default = raw.get("default", {}) or {}
    default_instruction = bool(default.get("instruction", False))

    delegations = raw.get("delegations", []) or []
    if not isinstance(delegations, list):
        raise PolicyError("`delegations` must be a list")

    rules: list[DelegationRule] = []
    for i, d in enumerate(delegations):
        if not isinstance(d, dict):
            raise PolicyError(f"delegation #{i} must be a mapping")
        source = d.get("source")
        if not isinstance(source, str) or not source.strip():
            raise PolicyError(f"delegation #{i} missing `source`")
        harness = d.get("harness")
        if harness is not None and not isinstance(harness, str):
            raise PolicyError(f"delegation #{i} harness must be string or omitted")
        ctx = d.get("context", {}) or {}
        paths = ctx.get("paths", []) or []
        if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
            raise PolicyError(f"delegation #{i} context.paths must be list of strings")
        auth = d.get("authority", {}) or {}
        if "instruction" not in auth:
            raise PolicyError(f"delegation #{i} missing authority.instruction")
        rules.append(DelegationRule(
            source=source.strip(),
            context_paths=tuple(paths),
            harness=harness,
            instruction_delegated=bool(auth["instruction"]),
            origin_line=i,
        ))
    return DelegationPolicy(
        version=version,
        rules=tuple(rules),
        default_instruction=default_instruction,
    )


# ---------------------------------------------------------------------------
# The D(s, c) evaluator
# ---------------------------------------------------------------------------

def _path_matches(context_path: str, patterns: Iterable[str]) -> bool:
    """Does context_path match any of the given glob patterns?

    Uses pathspec (gitignore syntax) when available; falls back to a
    conservative fnmatch-based check otherwise. Empty patterns list means
    "matches any context".
    """
    patterns = tuple(patterns)
    if not patterns:
        return True
    if _HAS_PATHSPEC:
        spec = PathSpec.from_lines("gitignore", patterns)
        return spec.match_file(context_path)
    # Fallback: fnmatch on each pattern
    import fnmatch
    for p in patterns:
        # Normalize gitignore-style ** to fnmatch's *
        p_norm = p.replace("**/", "").replace("/**", "").replace("**", "*")
        if fnmatch.fnmatch(context_path, p_norm):
            return True
    return False


def _source_matches(rule_source: str, query_source: str) -> bool:
    """Does the query source match the rule's source?

    Exact match is the base case. A trailing "@*" wildcard on the rule
    matches any version of the same package. A "pkg:npm/foo" without an
    "@version" fragment matches any version of foo.
    """
    if rule_source == query_source:
        return True
    if rule_source.endswith("@*"):
        prefix = rule_source[:-2]
        return query_source.startswith(prefix + "@")
    if "@" not in rule_source and query_source.startswith(rule_source + "@"):
        return True
    return False


def evaluate(
    policy: DelegationPolicy,
    source: str,
    context_path: str,
    harness: str,
) -> DelegationVerdict:
    """Return the delegation verdict for (source, context_path, harness).

    Semantics:
      1. Negative rules (instruction: false) that match take precedence.
      2. Positive rules (instruction: true) that match delegate authority.
      3. If no rule matches, the default is used.
    """
    negatives: list[DelegationRule] = []
    positives: list[DelegationRule] = []
    for rule in policy.rules:
        if not _source_matches(rule.source, source):
            continue
        if rule.harness is not None and rule.harness != harness:
            continue
        if not _path_matches(context_path, rule.context_paths):
            continue
        if rule.instruction_delegated:
            positives.append(rule)
        else:
            negatives.append(rule)

    if negatives:
        r = negatives[0]
        return DelegationVerdict(
            delegated=False,
            matched_rule=r,
            matched_by="negative",
            reason=(f"source {source!r} explicitly NOT delegated over "
                    f"{context_path!r} by rule #{r.origin_line}"),
        )
    if positives:
        r = positives[0]
        return DelegationVerdict(
            delegated=True,
            matched_rule=r,
            matched_by="positive",
            reason=(f"source {source!r} explicitly delegated over "
                    f"{context_path!r} by rule #{r.origin_line}"),
        )
    return DelegationVerdict(
        delegated=policy.default_instruction,
        matched_rule=None,
        matched_by="default",
        reason=(f"no rule matched (source={source!r}, context={context_path!r}, "
                f"harness={harness!r}); default.instruction="
                f"{policy.default_instruction}"),
    )


# ---------------------------------------------------------------------------
# Provenance -> policy-source mapping
# ---------------------------------------------------------------------------

_PURL_PREFIX = {
    "npm": "pkg:npm/",
    "cargo": "pkg:cargo/",
    "golang": "pkg:golang/",
    "go": "pkg:golang/",
    "pypi": "pkg:pypi/",
    "maven": "pkg:maven/",
}


def manifest_entry_to_source(entry: dict[str, Any]) -> str:
    """Convert an Ovrin manifest entry's origin block into a policy-source ID.

    Uses purl when a package identity is available; falls back to repo:*
    identifiers for first-party classes.
    """
    origin = entry.get("origin", {}) or {}
    cls = origin.get("class", "unknown")
    pkg = origin.get("package")  # dict {"ecosystem","name","version"} or "name@version" string
    path = entry.get("path", "") or ""

    eco = None
    name = None
    version = None
    if isinstance(pkg, dict):
        eco = str(pkg.get("ecosystem", "")).lower() or None
        name = pkg.get("name") or None
        v = pkg.get("version")
        version = str(v) if v not in (None, "", "unknown") else None
    elif isinstance(pkg, str) and pkg.strip():
        s = pkg.strip()
        if "@" in s:
            name, _, version = s.rpartition("@")
            name = name or None
            version = version or None
            if version in ("", "unknown"):
                version = None
        else:
            name = s
        # origin.py resolves a package identity only for npm (node_modules) today
        eco = "npm"

    # Fallback ecosystem inference for npm paths when none was recorded.
    if name and not eco and "node_modules/" in path.replace("\\", "/"):
        eco = "npm"

    if name and eco:
        prefix = _PURL_PREFIX.get(eco)
        if prefix:
            return f"{prefix}{name}@{version}" if version else f"{prefix}{name}"

    if cls == "repo":
        return "repo:default"
    if cls == "workspace":
        # workspace identity might be in origin.workspace
        ws = (origin.get("workspace") or {}).get("name", "unnamed")
        return f"repo:workspace/{ws}"
    if cls == "submodule":
        sm = (origin.get("submodule") or {}).get("path", entry.get("path", "unknown"))
        return f"repo:submodule/{sm}"
    if cls == "untracked":
        return "repo:untracked"
    return f"unknown:{entry.get('path', '?')}"


# ---------------------------------------------------------------------------
# Example policy generation (for docs and tests)
# ---------------------------------------------------------------------------

EXAMPLE_POLICY_TEXT = """\
# Ovrin authority-policy.yaml
# Declares D(s, c): which instruction sources may govern which contexts.
version: 1

# Deny-by-default: an unknown source may not govern an unknown context.
default:
  instruction: false

delegations:
  # First-party repository files can govern any first-party context.
  - source: "repo:default"
    context:
      paths: []           # empty = any context
    authority:
      instruction: true

  # An in-house policy pack, delivered as a dependency, is trusted for
  # its own vendored subtree only.
  - source: "pkg:npm/example-policy@*"
    context:
      paths: ["vendor/example/**"]
    authority:
      instruction: true

  # But that same policy pack is NOT delegated over the security config.
  # The negative rule wins over any positive rule that also matches.
  - source: "pkg:npm/example-policy@*"
    context:
      paths: ["config/security/**", ".github/workflows/**"]
    authority:
      instruction: false
"""


def emit_example_policy() -> str:
    """Return the example policy YAML shipped with Ovrin."""
    return EXAMPLE_POLICY_TEXT
