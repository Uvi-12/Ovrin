"""Ovrin enforce — the provenance-to-authority binding layer.

Three layers in one module, operating in sequence:

  LAYER 1 — STATIC PRE-FLIGHT GATE
    Blocks instruction files whose origin, governance, and predicted
    reachability together indicate an unauthorized authority acquisition,
    before the agent ever starts. Deterministic: every decision traces to
    three manifest fields already computed by `ovrin scan`.

  LAYER 2 — IMPORT-DELEGATION AUDIT
    Detects first-party instruction files that contain @import directives
    pointing to third-party paths. The import act itself is the authority-
    granting event, not the imported file's existence. Flags the DELEGATION
    DECISION — the first-party file that chose to import — rather than the
    imported artifact, because that is where a reviewer can intervene.
    This is the layer that addresses the import-carriage finding (172/200
    and 198/200): the boundary the paper identified is at the import
    declaration, so that is where the control lives.

  LAYER 3 — UNCERTAINTY DISCLOSURE
    Produces a machine-readable uncertainty manifest alongside every
    decision. Reports NOT only what is blocked and what is allowed, but
    also: resolver confidence for each reachability verdict, whether the
    import chain was fully resolved or partially unknown, and which files
    could not be classified with certainty. A gate that reports its own
    uncertainty is categorically different from one that pretends
    determinism it does not have — and from any existing supply-chain or
    SBOM tool, none of which publish inline uncertainty for their own
    decisions.

Together these three layers implement the paper's missing primitive:
  "a reviewable binding between artifact provenance and runtime authority."

The static gate addresses the discovery and tool-read-carriage channels.
The import audit addresses the import-carriage channel.
Uncertainty disclosure converts the resolver's known limitations (3/6 accuracy
in the paper's own evaluation) from a weakness into a first-class output.

Usage:
    from ovrin.enforce import enforce_all, EnforceResult
    result = enforce_all(manifest, harness_id="claude-code", root=Path("."))
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ovrin import delegation as _delegation
from ovrin.delegation import (
    DelegationPolicy,
    DelegationVerdict,
    manifest_entry_to_source,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCKABLE_ORIGINS = frozenset({"vendored", "submodule", "installed-dependency"})
CONFIDENCE_RANK = {"observed": 3, "documented": 2, "inferred": 1, "unknown": 0}

# @import patterns for known harnesses. Claude Code uses @path, Gemini uses
# @path. We parse both the bare @path form and the explicit @import form.
IMPORT_RE = re.compile(
    r"^\s*@(?:import\s+)?([^\s#]+)",
    re.MULTILINE,
)

# Harnesses known to follow @import directives
IMPORT_HARNESSES = frozenset({"claude-code", "gemini-cli"})


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Uncertainty:
    """What we do not know about a decision. Exposed to the caller so they
    can decide whether to escalate, warn, or silently allow."""
    resolver_confidence: str      # observed | documented | inferred | unknown
    import_chain_complete: bool   # True if every @import target was resolved
    unresolved_imports: tuple[str, ...] = ()   # targets we could not classify
    note: str = ""


@dataclass(frozen=True)
class Decision:
    """One enforcement decision for one instruction file."""
    path: str
    origin_cls: str
    enforceable: bool | None
    reachability_verdict: str
    layer: str                    # "delegation-gate" | "static-gate" | "import-audit" | "allowed"
    action: str                   # "BLOCK" | "WARN" | "ALLOW"
    reason: str
    uncertainty: Uncertainty
    # D(P(x), c) evaluation for this file, when a policy was supplied.
    # None => no policy provided, so no delegation-based decision was made.
    a_h: int | None = None                     # A_h(x, c) in {0, 1}
    d_of_p_c: int | None = None                # D(P(x), c) in {0, 1}
    policy_source: str | None = None           # the identifier we looked up in D
    policy_match: str | None = None            # "positive" | "negative" | "default"

    def __str__(self) -> str:
        conf = self.uncertainty.resolver_confidence
        return (f"{self.action:5s}  [{self.layer}]  {self.path}"
                f"  (resolver-confidence={conf}  "
                f"reason={self.reason})")


@dataclass
class ImportDelegation:
    """A detected @import delegation in a first-party file."""
    importer_path: str            # the first-party file that contains @import
    import_target: str            # the raw import string, as written
    resolved_target: str | None   # resolved relative path, or None if unknown
    target_origin_cls: str | None # origin class of the resolved target
    target_enforceable: bool | None
    action: str                   # "FLAG" | "WARN" | "OK"
    reason: str
    uncertainty: Uncertainty


@dataclass
class EnforceResult:
    """Complete output of enforce_all()."""
    harness_id: str
    decisions: list[Decision] = field(default_factory=list)
    import_delegations: list[ImportDelegation] = field(default_factory=list)

    # Aggregate counts — the three MCPFixGen metrics
    blocked: int = 0             # BLOCK decisions from static gate
    flagged: int = 0             # FLAG decisions from import audit
    warned: int = 0              # WARN decisions (uncertain)
    allowed: int = 0             # ALLOW decisions

    # Uncertainty summary
    low_confidence_decisions: int = 0   # resolver_confidence in {inferred, unknown}
    unresolved_import_chains: int = 0   # import chains we could not fully trace

    def summary_line(self) -> str:
        return (f"blocked={self.blocked}  flagged={self.flagged}  "
                f"warned={self.warned}  allowed={self.allowed}  "
                f"low-confidence={self.low_confidence_decisions}  "
                f"unresolved-imports={self.unresolved_import_chains}")

    def has_findings(self) -> bool:
        return self.blocked > 0 or self.flagged > 0 or self.warned > 0


# ---------------------------------------------------------------------------
# Layer 0 — Delegation gate  (implements D(P(x), c) directly)
# ---------------------------------------------------------------------------
#
# The paper defines IAD as:  A_h(x, c) = 1  AND  D(P(x), c) = 0.
# The three-condition static gate below is a *heuristic approximation* of D.
# When the project ships an authority-policy.yaml, this gate becomes the
# ground truth: A_h is read from the reachability verdict, D is looked up
# in the policy, and the action follows directly from the definition.
# This is what turns Ovrin from a heuristic tool into a reference monitor
# for the paper's central primitive.

def _delegation_gate(
    entry: dict[str, Any],
    harness_id: str,
    policy: DelegationPolicy,
    context_path: str,
) -> Decision:
    """Evaluate one manifest entry directly against D(P(x), c).

    A_h(x, c) is derived from the harness-specific reachability verdict:
        loaded => A_h = 1
        any other verdict => A_h = 0

    D(P(x), c) is looked up in `policy` using the entry's provenance and
    the supplied context path.

    IAD holds  iff  A_h = 1  AND  D = 0.
    """
    origin_cls: str = entry["origin"]["class"]
    enforceable: bool | None = entry["review"].get("enforceable")
    reach: dict = entry.get("reachability", {}).get(harness_id, {})
    verdict: str = reach.get("verdict", "not-discovered")
    confidence: str = reach.get("confidence", "unknown")

    a_h = 1 if verdict == "loaded" else 0

    source = manifest_entry_to_source(entry)
    d_verdict: DelegationVerdict = _delegation.evaluate(
        policy, source, context_path, harness_id,
    )
    d = d_verdict.as_int()

    unc = Uncertainty(
        resolver_confidence=confidence,
        import_chain_complete=True,
        note="" if CONFIDENCE_RANK.get(confidence, 0) >= 2
              else (f"reachability verdict has low confidence "
                    f"({confidence!r}); block downgraded to WARN"),
    )

    # IAD: harness authorized a source the project did not delegate
    if a_h == 1 and d == 0:
        if CONFIDENCE_RANK.get(confidence, 0) < 2:
            return Decision(
                entry["path"], origin_cls, enforceable, verdict,
                "delegation-gate", "WARN",
                (f"A_h=1, D(P(x)={source!r}, c={context_path!r})=0, "
                 f"but reachability confidence={confidence!r}; "
                 f"{d_verdict.reason}"),
                unc,
                a_h=a_h, d_of_p_c=d,
                policy_source=source, policy_match=d_verdict.matched_by,
            )
        return Decision(
            entry["path"], origin_cls, enforceable, verdict,
            "delegation-gate", "BLOCK",
            (f"IAD: A_h=1 and D(P(x)={source!r}, c={context_path!r})=0. "
             f"{d_verdict.reason}"),
            unc,
            a_h=a_h, d_of_p_c=d,
            policy_source=source, policy_match=d_verdict.matched_by,
        )

    # Not IAD. Either the harness did not authorize the source, or the
    # project did delegate that source over that context.
    if a_h == 0:
        reason = (f"A_h=0 (reachability={verdict!r}); "
                  f"source {source!r} not resolved as authoritative")
    else:
        reason = (f"A_h=1 and D=1: {d_verdict.reason}")
    return Decision(
        entry["path"], origin_cls, enforceable, verdict,
        "delegation-gate", "ALLOW", reason, unc,
        a_h=a_h, d_of_p_c=d,
        policy_source=source, policy_match=d_verdict.matched_by,
    )


# ---------------------------------------------------------------------------
# Layer 1 — Static pre-flight gate  (heuristic approximation of D)
# ---------------------------------------------------------------------------

def _static_gate(entry: dict[str, Any], harness_id: str) -> Decision:
    """Evaluate one manifest entry against the three-condition block rule."""
    origin_cls: str = entry["origin"]["class"]
    enforceable: bool | None = entry["review"].get("enforceable")
    reach: dict = entry.get("reachability", {}).get(harness_id, {})
    verdict: str = reach.get("verdict", "not-discovered")
    confidence: str = reach.get("confidence", "unknown")

    unc = Uncertainty(
        resolver_confidence=confidence,
        import_chain_complete=True,  # static gate does not parse imports
        note="" if CONFIDENCE_RANK.get(confidence, 0) >= 2
              else f"reachability verdict has low confidence ({confidence!r}); "
                   "treat as WARN rather than BLOCK",
    )

    # Three-condition block
    if (
        origin_cls in BLOCKABLE_ORIGINS
        and enforceable is not True
        and verdict == "loaded"
    ):
        # Downgrade to WARN when resolver confidence is low, because a
        # high-confidence BLOCK on a shaky verdict causes false positives
        if CONFIDENCE_RANK.get(confidence, 0) < 2:
            return Decision(
                entry["path"], origin_cls, enforceable, verdict,
                "static-gate", "WARN",
                f"{origin_cls} origin; review.enforceable={enforceable!r}; "
                f"reachability={verdict!r} but confidence={confidence!r}",
                unc,
            )
        return Decision(
            entry["path"], origin_cls, enforceable, verdict,
            "static-gate", "BLOCK",
            f"{origin_cls} origin; not enforceably covered; "
            f"loaded by {harness_id!r} (confidence={confidence!r})",
            unc,
        )

    # Build allow reason
    parts = []
    if origin_cls not in BLOCKABLE_ORIGINS:
        parts.append(f"origin={origin_cls!r} (first-party)")
    if enforceable is True:
        parts.append("enforceably covered")
    if verdict != "loaded":
        parts.append(f"reachability={verdict!r}")
    reason = "; ".join(parts) if parts else "does not meet block conditions"

    return Decision(
        entry["path"], origin_cls, enforceable, verdict,
        "static-gate", "ALLOW", reason, unc,
    )


# ---------------------------------------------------------------------------
# Layer 2 — Import-delegation audit
# ---------------------------------------------------------------------------

def _parse_imports(text: str) -> list[str]:
    """Extract @import targets from an instruction file's text."""
    return [m.group(1).strip() for m in IMPORT_RE.finditer(text)]


def _resolve_import(importer_rel: str, target: str, root: Path) -> Path | None:
    """Resolve an @import target relative to the importer file's directory."""
    try:
        importer_dir = (root / importer_rel).parent
        resolved = (importer_dir / target).resolve()
        # Must stay inside the root
        resolved.relative_to(root.resolve())
        return resolved
    except (ValueError, OSError):
        return None


def _import_audit(
    entry: dict[str, Any],
    all_entries_by_rel: dict[str, dict],
    harness_id: str,
    root: Path,
) -> list[ImportDelegation]:
    """Audit @import directives in a first-party instruction file."""
    # Only audit first-party files for import harnesses
    if entry["origin"]["class"] not in {"repo", "workspace", "untracked"}:
        return []
    if harness_id not in IMPORT_HARNESSES:
        return []

    importer_path = entry["path"]
    abs_path = root / importer_path
    if not abs_path.is_file():
        return []

    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    targets = _parse_imports(text)
    if not targets:
        return []

    delegations = []
    for target in targets:
        resolved_abs = _resolve_import(importer_path, target, root)
        if resolved_abs is None:
            # Could not resolve — report as uncertain
            unc = Uncertainty(
                resolver_confidence="unknown",
                import_chain_complete=False,
                unresolved_imports=(target,),
                note="import target could not be resolved to a path inside the repository",
            )
            delegations.append(ImportDelegation(
                importer_path=importer_path,
                import_target=target,
                resolved_target=None,
                target_origin_cls=None,
                target_enforceable=None,
                action="WARN",
                reason=f"@import {target!r} could not be resolved; "
                       "cannot determine if target is third-party",
                uncertainty=unc,
            ))
            continue

        try:
            resolved_rel = resolved_abs.relative_to(root.resolve()).as_posix()
        except ValueError:
            resolved_rel = None

        target_entry = all_entries_by_rel.get(resolved_rel) if resolved_rel else None
        if target_entry is None:
            # Resolved path is not an instruction file in the manifest —
            # could be a non-instruction file being imported, which is unusual
            unc = Uncertainty(
                resolver_confidence="unknown",
                import_chain_complete=False,
                unresolved_imports=(target,),
                note="import target resolves to a path not in the instruction manifest",
            )
            delegations.append(ImportDelegation(
                importer_path=importer_path,
                import_target=target,
                resolved_target=resolved_rel,
                target_origin_cls=None,
                target_enforceable=None,
                action="WARN",
                reason=f"@import {target!r} resolves to {resolved_rel!r} which "
                       "is not a known instruction file",
                uncertainty=unc,
            ))
            continue

        t_origin = target_entry["origin"]["class"]
        t_enforceable = target_entry["review"].get("enforceable")
        t_confidence = (target_entry.get("reachability", {})
                        .get(harness_id, {}).get("confidence", "unknown"))

        unc = Uncertainty(
            resolver_confidence=t_confidence,
            import_chain_complete=True,
            note="",
        )

        if t_origin in BLOCKABLE_ORIGINS and t_enforceable is not True:
            # This is the finding: a reviewed first-party file is delegating
            # authority to an unreviewed third-party source via @import.
            # The delegation decision — the @import line — is in the first-
            # party file, so THAT file is what we flag. A reviewer who
            # approves the first-party file must also approve the transitive
            # import chain, but currently has no way to see it at review time.
            delegations.append(ImportDelegation(
                importer_path=importer_path,
                import_target=target,
                resolved_target=resolved_rel,
                target_origin_cls=t_origin,
                target_enforceable=t_enforceable,
                action="FLAG",
                reason=(
                    f"{importer_path!r} imports {resolved_rel!r} "
                    f"(origin={t_origin!r}, enforceable={t_enforceable!r}). "
                    f"Approving the importer does not approve this transitive "
                    f"delegation to a {t_origin} source."
                ),
                uncertainty=unc,
            ))
        else:
            delegations.append(ImportDelegation(
                importer_path=importer_path,
                import_target=target,
                resolved_target=resolved_rel,
                target_origin_cls=t_origin,
                target_enforceable=t_enforceable,
                action="OK",
                reason=f"@import target {resolved_rel!r} is {t_origin!r} "
                       f"and enforceable={t_enforceable!r}",
                uncertainty=unc,
            ))

    return delegations


# ---------------------------------------------------------------------------
# Layer 3 — Uncertainty manifest
# ---------------------------------------------------------------------------

def _aggregate_uncertainty(result: EnforceResult) -> None:
    """Populate aggregate uncertainty counts on the result in place."""
    for d in result.decisions:
        if CONFIDENCE_RANK.get(d.uncertainty.resolver_confidence, 0) < 2:
            result.low_confidence_decisions += 1
    for imp in result.import_delegations:
        if not imp.uncertainty.import_chain_complete:
            result.unresolved_import_chains += 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enforce_all(
    manifest: dict[str, Any],
    harness_id: str,
    root: Path,
    policy: DelegationPolicy | None = None,
    context_path: str = ".",
) -> EnforceResult:
    """Run all enforcement layers and return a unified EnforceResult.

    When `policy` is provided, Layer 0 (delegation gate) is the primary
    ground truth: it computes A_h and D directly and returns BLOCK / WARN /
    ALLOW from the definition IAD <=> A_h=1 AND D=0. The static gate is
    then not run for that entry, because the delegation gate already made
    the decision on principled grounds.

    When `policy` is None, the original static gate (Layer 1) is used as
    a heuristic. This preserves the earlier behavior and is what the paper
    describes as "the current three-condition block rule".

    Layer 2 (import audit) runs in either mode.
    Layer 3 (uncertainty) aggregates confidence across all decisions.
    """
    result = EnforceResult(harness_id=harness_id)
    entries = manifest.get("instructions", [])
    by_rel = {e["path"]: e for e in entries}

    for entry in entries:
        # Layer 0 if a policy is present; otherwise Layer 1.
        if policy is not None:
            dec = _delegation_gate(entry, harness_id, policy, context_path)
        else:
            dec = _static_gate(entry, harness_id)
        result.decisions.append(dec)
        if dec.action == "BLOCK":
            result.blocked += 1
        elif dec.action == "WARN":
            result.warned += 1
        else:
            result.allowed += 1

        # Layer 2 (unchanged)
        delegations = _import_audit(entry, by_rel, harness_id, root)
        for imp in delegations:
            result.import_delegations.append(imp)
            if imp.action == "FLAG":
                result.flagged += 1

    # Post-process: @import-flagged targets are loaded via import chain.
    # Feed A_h=1 back into the delegation gate so IAD fires correctly.
    imported_paths = {
        imp.resolved_target
        for imp in result.import_delegations
        if imp.action == "FLAG" and imp.resolved_target
    }
    for i, dec in enumerate(result.decisions):
        if dec.path not in imported_paths:
            continue
        if dec.a_h == 1:
            continue
        entry = by_rel.get(dec.path, {})
        if policy is not None:
            source = manifest_entry_to_source(entry)
            d_verdict = _delegation.evaluate(policy, source, context_path, harness_id)
            d = d_verdict.as_int()
            unc = Uncertainty(
                resolver_confidence=dec.uncertainty.resolver_confidence,
                import_chain_complete=True,
                note="A_h promoted to 1 via @import delegation finding",
            )
            if d == 0:
                new_action = "BLOCK"
                new_reason = (
                    f"IAD via @import: A_h=1 (loaded by import chain) and "
                    f"D(P(x)={source!r}, c={context_path!r})=0. "
                    f"{d_verdict.reason}"
                )
            else:
                new_action = "ALLOW"
                new_reason = f"@import target: A_h=1 and D=1: {d_verdict.reason}"
            new_dec = Decision(
                dec.path, dec.origin_cls, dec.enforceable,
                dec.reachability_verdict,
                "delegation-gate", new_action, new_reason, unc,
                a_h=1, d_of_p_c=d,
                policy_source=source, policy_match=d_verdict.matched_by,
            )
            if dec.action != new_dec.action:
                if dec.action == "ALLOW":
                    result.allowed -= 1
                elif dec.action == "WARN":
                    result.warned -= 1
                if new_dec.action == "BLOCK":
                    result.blocked += 1
                elif new_dec.action == "WARN":
                    result.warned += 1
                elif new_dec.action == "ALLOW":
                    result.allowed += 1
            result.decisions[i] = new_dec

    # Layer 3 — Uncertainty manifest
    _aggregate_uncertainty(result)
    return result


def quarantine(root: Path, result: EnforceResult,
               quarantine_dir: Path) -> list[str]:
    """Move BLOCK-ed files to quarantine_dir so the agent cannot read them.
    WARN and FLAG decisions are not moved — they require human review, not
    automated removal. Returns list of moved paths.
    """
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for d in result.decisions:
        if d.action != "BLOCK":
            continue
        src = root / d.path
        if not src.exists():
            continue
        dst = quarantine_dir / d.path.replace("/", "__SLASH__")
        shutil.move(str(src), str(dst))
        moved.append(d.path)
    return moved


def restore(root: Path, quarantine_dir: Path) -> list[str]:
    """Restore quarantined files to their original paths."""
    restored: list[str] = []
    if not quarantine_dir.exists():
        return restored
    for dst in quarantine_dir.iterdir():
        rel = dst.name.replace("__SLASH__", "/")
        src = root / rel
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
        restored.append(rel)
    return restored


def to_sarif(result: EnforceResult, tool_version: str = "0.1.0") -> dict:
    """Emit a SARIF 2.1.0 document for the enforce result.

    SARIF is the standard interchange format for static analysis findings.
    Emitting it means Ovrin's enforce output can be consumed by GitHub
    Advanced Security, Azure DevOps, and any SARIF-aware CI system without
    adapter code. This is the integration path for CI policy gating.
    """
    runs_results = []
    rules = {}

    for d in result.decisions:
        if d.action not in ("BLOCK", "WARN"):
            continue
        rule_id = f"IAD-{d.layer.upper().replace('-', '_')}-{d.action}"
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": f"InstructionAuthorityDivergence/{d.layer}/{d.action}",
                "shortDescription": {"text": d.reason},
                "properties": {
                    "tags": ["supply-chain", "agent-security",
                             "instruction-authority"],
                },
            }
        runs_results.append({
            "ruleId": rule_id,
            "level": "error" if d.action == "BLOCK" else "warning",
            "message": {"text": d.reason},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": d.path},
                },
            }],
            "properties": {
                "originClass": d.origin_cls,
                "enforceable": d.enforceable,
                "reachabilityVerdict": d.reachability_verdict,
                "resolverConfidence": d.uncertainty.resolver_confidence,
            },
        })

    for imp in result.import_delegations:
        if imp.action not in ("FLAG", "WARN"):
            continue
        rule_id = "IAD-IMPORT_DELEGATION-FLAG"
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": "InstructionAuthorityDivergence/ImportDelegation",
                "shortDescription": {
                    "text": "First-party instruction file delegates authority "
                            "to an unreviewed third-party source via @import"
                },
                "properties": {
                    "tags": ["supply-chain", "agent-security",
                             "import-delegation"],
                },
            }
        runs_results.append({
            "ruleId": rule_id,
            "level": "error" if imp.action == "FLAG" else "warning",
            "message": {"text": imp.reason},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": imp.importer_path},
                },
            }],
            "properties": {
                "importTarget": imp.import_target,
                "resolvedTarget": imp.resolved_target,
                "targetOriginClass": imp.target_origin_cls,
                "importChainComplete": imp.uncertainty.import_chain_complete,
            },
        })

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "ovrin",
                    "version": tool_version,
                    "informationUri": "https://github.com/Uvi-12/ovrin",
                    "rules": list(rules.values()),
                },
            },
            "results": runs_results,
            "properties": {
                "harness": result.harness_id,
                "blocked": result.blocked,
                "flagged": result.flagged,
                "warned": result.warned,
                "lowConfidenceDecisions": result.low_confidence_decisions,
                "unresolvedImportChains": result.unresolved_import_chains,
            },
        }],
    }
