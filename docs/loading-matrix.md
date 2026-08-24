# The loading matrix

Which coding agents discover which instruction files, and under what conditions.

Confidence is recorded per behavioural claim (root loading, nested loading,
ancestor loading, ignore behaviour, override semantics), not once per agent, so
one observed test cannot silently upgrade untested claims. Read the confidence
of the specific claim before citing it.

| Level | Meaning |
| --- | --- |
| `observed` | We ran the agent and watched it load, or not load, the file. A reproduction exists under `tests/harness_cases/`. |
| `documented` | The vendor documents this behaviour. We have not verified it. |
| `inferred` | Read from source or public docs, not executed. |
| `unknown` | Placeholder. Do not cite. |

## Current state, verified August 2026

| Agent | Native file | Reads AGENTS.md | Walks tree | Walks ancestors | Respects ignore | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| Codex CLI | `AGENTS.md` | yes | yes | yes | unknown | documented |
| Claude Code | `CLAUDE.md` | no | yes | yes | unknown | documented |
| Gemini CLI | `GEMINI.md` | configurable | yes | yes | yes | documented |
| Cursor | `.cursor/rules` | yes | yes | no | unknown | documented |
| GitHub Copilot | `.github/copilot-instructions.md` | yes | no | no | n/a | documented |
| Devin Desktop | `.devin/rules/` | yes | yes | unknown | unknown | documented |
| Amp | `AGENTS.md` | yes | unknown | unknown | unknown | documented |
| goose | `.goosehints` | no | no | no | unknown | unknown |
| Cline | `.clinerules` | no | no | no | unknown | inferred |
| Continue | `.continue/rules` | no | no | no | unknown | unknown |
| aider | `CONVENTIONS.md` | manual | no | no | n/a | documented |

Notes worth carrying into any talk:

- Devin Desktop is the former Windsurf, renamed 2 June 2026, and matches filenames case-insensitively.
- Amp created the singular `AGENT.md` in May 2025 and adopted `AGENTS.md` on 20 August 2025. Old repos still carry `AGENT.md`.
- Codex reads `AGENTS.override.md`, but it does not replace ancestor instructions. Codex combines instruction files from the repository root down to the working directory; `AGENTS.override.md` only takes precedence over `AGENTS.md` within its own directory. Root and nested instructions are both in context. Codex truncates a project doc at 32 KiB by default.
- Gemini CLI reads `AGENTS.md` only when configured, and it respects ignore rules, so it does not read `node_modules`.
- Claude Code does not read `AGENTS.md` at all.

## Why the ignore column decides the third-party question

The naive claim is that any instruction file inside a dependency reaches the agent. That is not true in general.

An agent that respects ignore rules does not scan `node_modules`, because `node_modules` is git-ignored in nearly every JavaScript project. For those agents the npm case is closed.

But ignore rules do not cover everything a third party can ship:

- Vendored source trees. `vendor/`, `third_party/`, Go vendoring. These are committed, so they are not ignored, and any tree-walking agent reads them.
- Git submodules. Tracked by definition.
- Workspace members. A monorepo sibling is first-class source.
- Any agent that does not consult ignore files at all.

So the useful question is not "do instruction files inherit" but: under which discovery, ignore, and workspace rules does a third-party instruction file enter the active context? That is what the `reachability` field answers, per file and per agent, and it is why Ovrin says `unverified` instead of guessing.

## Open questions

1. When a root instruction and a nested `AGENTS.override.md` are both in context, can the nested, more-specific guidance behaviorally defeat a broader safety restriction set at the root? This is a precedence-conflict question, not file replacement: the root instruction is not deleted, so the test is whether later, more-specific guidance wins in practice.
2. Does case-insensitive matching create a second discovery surface that a case-sensitive CODEOWNERS rule misses?
3. Do ancestor-walking agents read files above the repository root, for example on a CI runner with several checkouts under one parent?
4. Are ignore rules consulted for discovery, for reading, or both?

Contributions welcome. See [../CONTRIBUTING.md](../CONTRIBUTING.md).
