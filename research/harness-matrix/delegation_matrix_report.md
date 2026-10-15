# Delegation-Policy Matrix: 2x2 Evaluation

Isolates the paper's central claim that neither origin class
nor CODEOWNERS coverage is the delegation decision.

## Policy under test

```yaml
version: 1
default:
  instruction: false
delegations:
  # Cell 1: first-party is delegated over src/
  - source: "repo:default"
    context:
      paths: ["src/**"]
    authority:
      instruction: true

  # Cell 3: policy-pack is delegated over its own subtree
  - source: "pkg:npm/policy-pack@1.0.0"
    context:
      paths: ["vendor/policy-pack/**"]
    authority:
      instruction: true

  # Cell 2 and Cell 4: no positive rule; default (deny) fires.
```

## Cells

| Cell | Origin | Governance | D(s,c) | Expected | N | Delegation gate agree | Static-baseline agree |
|---|---|---|---|---|---|---|---|
| Cell 1 (first-party, covered, delegated) | repo | covered | 1 | ALLOW | 50 | 50/50 | 50/50 |
| Cell 2 (third-party, covered, NOT delegated) | installed-dependency | covered | 0 | BLOCK | 50 | 50/50 | 0/50 |
| Cell 3 (third-party, uncovered, delegated) | installed-dependency | uncovered | 1 | ALLOW | 50 | 50/50 | 0/50 |
| Cell 4 (third-party, uncovered, NOT delegated) | installed-dependency | uncovered | 0 | BLOCK | 50 | 50/50 | 50/50 |

## Aggregate

- Delegation gate: **200/200 correct** across the 2x2.
- Static heuristic baseline: **100/200 correct** across the 2x2.

## Reading

Cell 2 (third-party, CODEOWNERS-covered, not delegated) is the
**paper's central discriminator**. A gate that treats governance as
delegation will ALLOW here. The delegation gate BLOCKs it, exactly
because D(s,c)=0 despite governance coverage. This isolates the
claim `reviewed != authorized`.

Cell 3 (third-party, uncovered, delegated) is the counterpart. A
gate that treats third-party origin as unauthorized will BLOCK
here. The delegation gate ALLOWs it because D(s,c)=1. This
isolates the claim `third-party != unauthorized`.
