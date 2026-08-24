# Seam 3 — Cross-harness instruction-authority divergence matrix

No two coding-agent harnesses resolve instruction authority the same way. This matrix
assembles (a) what each harness's PRIMARY DOCS say about discovery/precedence, and
(b) what Ovrin MEASURED where it ran an agent. The point is the divergence itself:
there is no uniform instruction-authority model across harnesses, so "a dependency
instruction file" has different power depending on which agent reads it.

Legend: MEASURED = Ovrin ran this and observed it; DOCS = from primary documentation;
— = not applicable / not shipped.

## Discovery & precedence model (from primary docs)

| Harness | Nested discovery | Precedence rule | Import/@-include | Ovrin measured |
| --- | --- | --- | --- | --- |
| Claude Code | Just-in-time on subtree access; root at launch | Deeper/nearer combines; @import splices file contents inline (≤4 hops) | **Yes** (`@path`, ext-import approval) | **the import-carriage mechanism: dep→first-party via @import 86–94%/50; the workspace-trust experiment provenance-blind 5/5; boundA autonomous holds 5/5; boundB restriction holds 5/5** |
| Codex CLI | Aggregates root→cwd | **Positional**: files closer to cwd appear later in the concatenated prompt and override earlier; deeper-scoped AGENTS wins in-scope | `@include` is an OPEN feature request (#17401), **not shipped** | **the precedence experiment scoped: dependency-local precedence 6/6** (deeper dep rule beat host root for a dep-local file) |
| Copilot (IDE) | Repository instructions | **Nearest** AGENTS.md takes precedence (documented) | n/a | not run |
| Copilot (CLI) | Combines applicable files | **No general precedence order defined** (undefined → unpredictable) | n/a | not run |
| Windsurf | Root always active; nested → auto path-glob | Activation by path glob on read/edit in subtree | n/a | not run |
| Amp | Parent/CWD loaded; subtree included on access | Traversal-triggered inclusion (not a stated nearest-wins resolver) | n/a | not run |
| VS Code agent | Nested AGENTS.md experimental; recursively added | **Agent decides** applicability (no enforced resolver) | n/a | not run |
| Gemini CLI | Hierarchical + just-in-time context discovery | Hierarchical; import processor validates path is within allowed dirs | **Yes** (`@` imports, gitignore-respecting option) | not run (free-tier quota) |

## What the divergence establishes

- **The same artifact has different authority per harness.** A `vendor/foo/AGENTS.md`
  is: positionally-dominant in Codex (if deep and in-scope), nearest-wins in
  Copilot-IDE, undefined in Copilot-CLI, glob-activated in Windsurf, agent-judged in
  VS Code, and import-reachable into first-party scope in Claude Code. No common model.
- **The import channel is not universal.** Claude Code and Gemini have `@` imports
  (the the import-carriage mechanism cross-boundary channel); Codex does NOT yet (feature request open). So
  the the import-carriage mechanism cross-boundary result is Claude-Code-specific *because the channel is*.
- **Provenance is nowhere a first-class input.** Every model above keys on filesystem
  location / discovery / position — none keys on software provenance. That is the
  common gap Ovrin identifies, independent of which resolution rule a harness uses.

## Honest bounds
- Rows marked DOCS are from primary documentation, not Ovrin measurement; Ovrin only
  measured Claude Code (the import-carriage mechanism, the workspace-trust experiment, bounds) and Codex (the precedence experiment scoped precedence).
- Cross-harness measurement at scale (running the same fixtures on Windsurf/Amp/
  Copilot/Gemini) is explicitly FUTURE WORK, not claimed here.
- The claim is "no uniform model + provenance is never first-class," which the docs
  support; it is not "we ran all of them."
