# Seam 2 — dependency depth of carried instruction files

Pure analysis of existing RQ3 carriage data (no agent runs). Depth = number
of path separators in the carried file's path (root file = depth 0).
Under positional precedence (Codex concatenates root->leaf; deeper = later =
overriding), deeper files occupy the dominant slots for work in their subtree.

## Pooled (all ecosystems)
- Carried instruction files analyzed: **431**
- Inside a dependency tree (vendor/node_modules/etc): **420 (97.4%)**
- Depth: min 2, median **2**, mean 2.53, max 6
- Depth distribution: {2: 286, 3: 86, 4: 41, 5: 13, 6: 5}

## Per ecosystem

| Ecosystem | carried files | in dep-tree | in-tree % | median depth | mean | max |
| --- | --- | --- | --- | --- | --- | --- |
| cargo | 302 | 302 | 100.0% | 2.0 | 2.17 | 4 |
| go | 71 | 71 | 100.0% | 4 | 3.85 | 6 |
| npm | 47 | 47 | 100.0% | 2 | 2.51 | 6 |
| python | 11 | 0 | 0.0% | 4 | 3.82 | 4 |

## Deepest example per ecosystem

- **cargo** (depth 4): `_v/uc-application/src/facade/AGENTS.md`
- **go** (depth 6): `vendor/github.com/twmb/franz-go/pkg/kgo/CLAUDE.md`
- **npm** (depth 6): `node_modules/netlify-cli/node_modules/fastify/node_modules/thread-stream/CLAUDE.md`
- **python** (depth 4): `_s/ansible_collections/kubevirt/core/AGENTS.md`

## Honest reading
- These are carried third-party instruction files from ordinary dependency
  materialization. Their depth is a property of dependency layout, not intent.
- Deeper placement => later position under root->leaf concatenation => higher
  positional precedence for tasks within that subtree (Codex-documented).
- This does NOT by itself prove cross-boundary control (that is Seam 1); it
  shows the raw material sits in positionally-dominant, dependency-tree
  locations, connecting the carriage measurement to the precedence mechanism.
- Depth is a structural fact; it is agent-independent. The precedence
  CONSEQUENCE of depth is agent-specific (Codex positional; others differ).
