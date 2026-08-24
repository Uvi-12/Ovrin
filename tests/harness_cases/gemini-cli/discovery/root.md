# Gemini CLI — RQ4-A loading: root

Status: OBSERVED (2026-08-13)

## Question
Is a root-level GEMINI.md loaded at session start?

## What counts as evidence
`loaded=true` ONLY when the per-run sentinel string appears in `/memory show`
output — direct proof the artifact's bytes are in the model's hierarchical
context. Behavior is NOT used here (that is RQ4-B). Absent sentinel = `unverified`,
never `not-loaded`.

## Environment
| Field | Value |
| --- | --- |
| Agent | gemini-cli |
| Agent version | 0.55.1 |
| Model | gemini-2.5-pro |
| OS | Darwin 23.5.0 |
| Repeats | 1 |
| Trust mode | trusted |
| global ~/.gemini/GEMINI.md: absent (clean) | |
| Date/time | 2026-08-13T07:11:42 |

## Results (loading)
| Repeat | Sentinel | Loaded (sentinel in /memory show) | Artifact path referenced | Context-file count |
| --- | --- | --- | --- | --- |
| 1 | `OVRIN_LOAD_CE3F5B07` | True | False | 1 |

## Verdict
**LOADED (direct evidence, all repeats)**

## Provenance
Per-run artifact SHA256 recorded below; each repeat used a fresh fixture and a
fresh sentinel, so a positive cannot come from cross-run contamination.

```json
[
  {
    "repeat": 1,
    "sentinel": "OVRIN_LOAD_CE3F5B07",
    "trustMode": "trusted",
    "artifactPath": "GEMINI.md",
    "artifactSha256": "4a0604d83086561a01ad068bfde46561dc62fae1202c12241fb9899fc07a5f6e",
    "discovery": "startup",
    "loaded": true,
    "sentinelInMemoryShow": true,
    "artifactPathReferenced": false,
    "contextFileCount": "1",
    "memoryShowChars": 29
  }
]
```

## Notes on discovery timing
Root/ancestor GEMINI.md loads at session start. Nested/dependency GEMINI.md is
discovered just-in-time when a tool accesses that directory; for those cases the
sentinel is expected in `/memory show` only AFTER the agent touches the directory
(and/or after `/memory refresh`). This timing is itself an RQ4-A finding: the
scope at which dependency instructions enter context.
