"""Tests for the delegation module and Layer 0 gate.

Covers:
  - policy loading and validation
  - D(s, c) semantics: positive/negative/default, negative-wins
  - source matching (exact, @* wildcard, no-version implies any-version)
  - context path matching (empty = any, glob, ** globs)
  - end-to-end enforce_all with a policy
  - the 2x2 matrix experiment (Case B: governance x delegation)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ovrin import delegation as dg
from ovrin.enforce import enforce_all
from ovrin.delegation import (
    DelegationPolicy,
    PolicyError,
    evaluate,
    load_policy_from_string,
    manifest_entry_to_source,
)


# ---------- basic loading -----------------------------------------------

def test_policy_loads_from_string():
    p = load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  - source: "repo:default"
    context:
      paths: []
    authority:
      instruction: true
""")
    assert p.version == 1
    assert p.default_instruction is False
    assert p.rule_count == 1
    assert p.rules[0].source == "repo:default"
    assert p.rules[0].instruction_delegated is True


def test_policy_rejects_bad_version():
    with pytest.raises(PolicyError):
        load_policy_from_string("version: 99\ndelegations: []\n")


def test_policy_rejects_missing_authority_instruction():
    with pytest.raises(PolicyError):
        load_policy_from_string("""
version: 1
delegations:
  - source: "repo:default"
    context: {}
    authority: {}
""")


# ---------- D(s, c) evaluation ------------------------------------------

@pytest.fixture
def three_rule_policy() -> DelegationPolicy:
    return load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  - source: "repo:default"
    authority:
      instruction: true
  - source: "pkg:npm/example-policy@1.4.2"
    context:
      paths: ["vendor/example/**"]
    authority:
      instruction: true
  - source: "pkg:npm/example-policy@1.4.2"
    context:
      paths: ["config/security/**"]
    authority:
      instruction: false
""")


def test_positive_match(three_rule_policy):
    v = evaluate(three_rule_policy, "repo:default", "src/foo.py", "claude-code")
    assert v.delegated is True
    assert v.matched_by == "positive"


def test_positive_in_scope(three_rule_policy):
    v = evaluate(
        three_rule_policy,
        "pkg:npm/example-policy@1.4.2",
        "vendor/example/lib/x.py",
        "claude-code",
    )
    assert v.delegated is True


def test_negative_wins_over_positive(three_rule_policy):
    # A rule delegating over vendor/example/** exists, but the query is in
    # config/security/**, where the negative rule applies.
    v = evaluate(
        three_rule_policy,
        "pkg:npm/example-policy@1.4.2",
        "config/security/allowlist.json",
        "claude-code",
    )
    assert v.delegated is False
    assert v.matched_by == "negative"


def test_default_when_no_rule_matches(three_rule_policy):
    v = evaluate(
        three_rule_policy,
        "pkg:npm/unrelated@1.0.0",
        "config/security/allowlist.json",
        "claude-code",
    )
    assert v.delegated is False
    assert v.matched_by == "default"


def test_wildcard_version_match():
    p = load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  - source: "pkg:npm/example-policy@*"
    context:
      paths: ["vendor/example/**"]
    authority:
      instruction: true
""")
    v = evaluate(p, "pkg:npm/example-policy@2.0.0", "vendor/example/x.py", "claude-code")
    assert v.delegated is True
    v = evaluate(p, "pkg:npm/example-policy@1.4.2", "vendor/example/x.py", "claude-code")
    assert v.delegated is True


def test_harness_scoped_rule_does_not_apply_to_other_harness():
    p = load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  - source: "repo:default"
    harness: "claude-code"
    authority:
      instruction: true
""")
    v = evaluate(p, "repo:default", "src/foo.py", "codex-cli")
    # No matching rule (harness mismatch), so default applies
    assert v.delegated is False
    assert v.matched_by == "default"

    v2 = evaluate(p, "repo:default", "src/foo.py", "claude-code")
    assert v2.delegated is True
    assert v2.matched_by == "positive"


# ---------- provenance -> policy source mapping -------------------------

def test_manifest_entry_to_source_first_party():
    e = {"path": "CLAUDE.md", "origin": {"class": "repo"}}
    assert manifest_entry_to_source(e) == "repo:default"


def test_manifest_entry_to_source_npm():
    e = {
        "path": "node_modules/foo/CLAUDE.md",
        "origin": {
            "class": "installed-dependency",
            "package": {"ecosystem": "npm", "name": "foo", "version": "1.2.3"},
        },
    }
    assert manifest_entry_to_source(e) == "pkg:npm/foo@1.2.3"


# ---------- end-to-end enforce_all with a policy ------------------------

def _mk_manifest(entries: list[dict]) -> dict:
    return {"instructions": entries}


def _mk_entry(path: str, origin_cls: str, verdict: str = "loaded",
              confidence: str = "documented", package: dict | None = None,
              enforceable: bool | None = None) -> dict:
    e = {
        "path": path,
        "origin": {"class": origin_cls},
        "review": {"ruleMatches": False, "enforceable": enforceable},
        "reachability": {
            "claude-code": {"verdict": verdict, "confidence": confidence},
        },
    }
    if package:
        e["origin"]["package"] = package
    return e


def test_enforce_all_delegated_third_party_is_allowed(tmp_path):
    """Case: third-party origin, but D(s,c)=1 by explicit delegation.
    The heuristic gate would BLOCK. The delegation gate must ALLOW."""
    policy = load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  - source: "pkg:npm/policy-pack@1.0.0"
    context:
      paths: ["vendor/policy-pack/**"]
    authority:
      instruction: true
""")
    manifest = _mk_manifest([
        _mk_entry(
            "vendor/policy-pack/CLAUDE.md",
            origin_cls="installed-dependency",
            package={"ecosystem": "npm", "name": "policy-pack", "version": "1.0.0"},
        ),
    ])
    r = enforce_all(manifest, "claude-code", tmp_path, policy=policy,
                    context_path="vendor/policy-pack/README.md")
    assert r.blocked == 0
    assert r.allowed == 1
    dec = r.decisions[0]
    assert dec.a_h == 1
    assert dec.d_of_p_c == 1
    assert dec.action == "ALLOW"
    assert dec.layer == "delegation-gate"


def test_enforce_all_undelegated_third_party_is_blocked(tmp_path):
    """Case: third-party origin, no delegation. Delegation gate BLOCKs."""
    policy = load_policy_from_string("""
version: 1
default:
  instruction: false
""")
    manifest = _mk_manifest([
        _mk_entry(
            "vendor/rogue/CLAUDE.md",
            origin_cls="installed-dependency",
            package={"ecosystem": "npm", "name": "rogue", "version": "0.1.0"},
        ),
    ])
    r = enforce_all(manifest, "claude-code", tmp_path, policy=policy,
                    context_path="src/main.py")
    assert r.blocked == 1
    dec = r.decisions[0]
    assert dec.a_h == 1
    assert dec.d_of_p_c == 0
    assert dec.action == "BLOCK"


def test_enforce_all_covered_but_undelegated_is_still_blocked(tmp_path):
    """Case: third-party origin, CODEOWNERS covered (enforceable=True),
    but D(s,c)=0. The heuristic static gate would ALLOW because
    enforceable=True. The delegation gate must BLOCK because governance
    is not delegation. This is the paper's core claim."""
    policy = load_policy_from_string("""
version: 1
default:
  instruction: false
""")
    manifest = _mk_manifest([
        _mk_entry(
            "vendor/rogue/CLAUDE.md",
            origin_cls="installed-dependency",
            enforceable=True,  # CODEOWNERS covered
            package={"ecosystem": "npm", "name": "rogue", "version": "0.1.0"},
        ),
    ])
    r = enforce_all(manifest, "claude-code", tmp_path, policy=policy,
                    context_path="src/main.py")
    assert r.blocked == 1
    dec = r.decisions[0]
    assert dec.d_of_p_c == 0
    assert dec.action == "BLOCK", (
        "Governance coverage must NOT imply delegation. If this test flips, "
        "the paper's central distinction has been silently violated."
    )


def test_enforce_all_first_party_undelegated_is_blocked(tmp_path):
    """Case: first-party origin, but the policy does NOT delegate first-party
    over this context. Delegation gate must BLOCK. This is the counterpart
    that shows 'first-party != delegated'."""
    policy = load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  - source: "repo:default"
    context:
      paths: ["src/**", "tests/**"]
    authority:
      instruction: true
""")
    manifest = _mk_manifest([
        _mk_entry("CLAUDE.md", origin_cls="repo"),
    ])
    r = enforce_all(manifest, "claude-code", tmp_path, policy=policy,
                    context_path="secrets/production.env")
    assert r.blocked == 1
    dec = r.decisions[0]
    assert dec.a_h == 1
    assert dec.d_of_p_c == 0


# ---------- the 2x2 matrix: governance × delegation ---------------------

def test_2x2_matrix_governance_x_delegation(tmp_path):
    """The paper's central experimental claim, encoded as one test.

    Four cells, one dimension = origin/governance (first-party vs third-party,
    CODEOWNERS-covered vs not), one dimension = delegation D(s, c). Correct
    actions come only from delegation, never from origin or governance alone.
    """
    policy = load_policy_from_string("""
version: 1
default:
  instruction: false
delegations:
  # first-party, covered, delegated
  - source: "repo:default"
    context:
      paths: ["src/**"]
    authority:
      instruction: true

  # third-party, uncovered, delegated (vendor policy pack over its own subtree)
  - source: "pkg:npm/policy-pack@1.0.0"
    context:
      paths: ["vendor/policy-pack/**"]
    authority:
      instruction: true

  # third-party, covered, NOT delegated over src/ (negative rule wins)
  - source: "pkg:npm/rogue@1.0.0"
    context:
      paths: ["src/**"]
    authority:
      instruction: false
""")

    # Cell 1: first-party, covered, delegated  -> ALLOW
    m1 = _mk_manifest([_mk_entry("CLAUDE.md", "repo", enforceable=True)])
    r1 = enforce_all(m1, "claude-code", tmp_path, policy=policy,
                     context_path="src/main.py")
    assert r1.allowed == 1
    assert r1.decisions[0].d_of_p_c == 1

    # Cell 2: third-party, covered, NOT delegated -> BLOCK
    m2 = _mk_manifest([_mk_entry(
        "vendor/rogue/CLAUDE.md",
        "installed-dependency",
        enforceable=True,   # governance covered
        package={"ecosystem": "npm", "name": "rogue", "version": "1.0.0"},
    )])
    r2 = enforce_all(m2, "claude-code", tmp_path, policy=policy,
                     context_path="src/main.py")
    assert r2.blocked == 1, "governance coverage without delegation must not allow"
    assert r2.decisions[0].d_of_p_c == 0

    # Cell 3: third-party, uncovered, delegated -> ALLOW
    m3 = _mk_manifest([_mk_entry(
        "vendor/policy-pack/CLAUDE.md",
        "installed-dependency",
        enforceable=None,   # governance not covered
        package={"ecosystem": "npm", "name": "policy-pack", "version": "1.0.0"},
    )])
    r3 = enforce_all(m3, "claude-code", tmp_path, policy=policy,
                     context_path="vendor/policy-pack/lib.py")
    assert r3.allowed == 1, "delegation without governance coverage must allow"
    assert r3.decisions[0].d_of_p_c == 1

    # Cell 4: third-party, uncovered, NOT delegated -> BLOCK
    m4 = _mk_manifest([_mk_entry(
        "vendor/unknown/CLAUDE.md",
        "installed-dependency",
        enforceable=None,
        package={"ecosystem": "npm", "name": "unknown", "version": "1.0.0"},
    )])
    r4 = enforce_all(m4, "claude-code", tmp_path, policy=policy,
                     context_path="src/main.py")
    assert r4.blocked == 1
    assert r4.decisions[0].d_of_p_c == 0


# ---------- backward compatibility: no policy => static-gate behavior ---

def test_no_policy_falls_back_to_static_gate(tmp_path):
    manifest = _mk_manifest([
        _mk_entry("vendor/x/CLAUDE.md", "installed-dependency"),
    ])
    r = enforce_all(manifest, "claude-code", tmp_path)  # no policy
    assert r.decisions[0].layer == "static-gate"
    # The static gate blocks third-party + not enforceable + loaded
    assert r.decisions[0].action == "BLOCK"
