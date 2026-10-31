# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-10-31

### Added
- Executing configuration in `ovrin scan`: `.mcp.json`, `.cursor/mcp.json`,
  `.gemini/settings.json`, `.claude/settings.json` and `.claude/settings.local.json`
  hooks, and `.claude/skills/*/SKILL.md`. Each file gets the same origin, review,
  and git facts as an instruction file, plus which agent loads it, what it can do
  (process execution, network egress, credential references, permission grants,
  unpinned packages, bundled scripts), and which dependency code its commands run.
- `--fail-on-exec-risk`: fails when root-loaded executing configuration runs code
  with no enforced review, or runs code that lives inside a dependency. Buried
  configuration, unpinned versions, and skills are reported as warnings only.
- `src/ovrin/data/exec_formats.yaml` with per-agent loading rules and confidence;
  Claude Code and Gemini CLI root loading are `observed` by the activation
  benchmark, Codex is recorded as not repository-local.
- Executing files in the SPDX export, an "Executing configuration" section in the
  table output, and a `fail-on-exec-risk` input on the GitHub Action.
- The example repository now includes a first-party pinned `.mcp.json`, a drive-by
  `.claude/settings.json` hook that runs a vendored script, and a buried vendored
  `.mcp.json`.

### Changed
- Manifest schema 0.2.0 adds `execRules`, `executing`, and `summary.executing`.
  Every 0.1.0 field is unchanged.
- The table header reads "Agent configuration manifest".

### Added earlier in this release cycle
- `ovrin keygen` / `ovrin sign` / `ovrin verify`: Ed25519 detached signatures over the
  manifest's canonical bytes (optional `[sign]` extra). Asymmetric by design, so a
  verifier cannot forge a manifest.
- Composite GitHub Action (`action.yml`), a `.github/workflows/scan.yml`, a pre-commit
  hook (`.pre-commit-hooks.yaml`), and a VS Code task (`examples/editor/`).
- A self-contained example (`examples/example-project/`): scan → gate → SPDX → enforce → sign.
- `scripts/promote-harness-claim.py` to flip a claim to `observed` after a real agent run,
  and `scripts/validate_spdx.py` for a structural SPDX check.
- Tests for the SPDX exporter, the `enforce` CLI + SARIF, manifest signing, and a
  `manifest.build()`-driven delegation integration test.

### Fixed
- Delegation: `manifest_entry_to_source` now maps the real `"name@version"` string
  (and scoped npm names) to a `pkg:` purl, not just the hand-built dict form, so policy
  rules match real manifests.
- `enforce` SARIF `informationUri` no longer points at the anonymized review URL.
- Modernized pathspec usage (gitignore factory) to drop a deprecation warning.

### Changed
- `harnesses` and the scan header report the matrix as *dated* and print claim coverage
  (observed/documented/inferred/unknown); no claim is labeled verified unless observed.

## [0.1.0] - 2026-08

### Added
- `ovrin scan` with table, JSON, and SPDX 3.0-aligned output.
- Origin classification: repo, workspace, submodule, vendored, installed-dependency, untracked.
- The `vendored` versus `installed-dependency` split, so a committed vendor tree and an installed package are not counted the same.
- CODEOWNERS resolution with last-match-wins, and a `ruleMatches` versus `enforceable` split so a catch-all rule is not reported as review.
- Per-agent reachability with explicit confidence levels and an `unverified` verdict.
- `introducedInAuthorsFirstCommit`, whether an instruction file was first added by an author's first commit to the repo.
- Complete-or-absent digests. A partial hash is never emitted.
- `--no-timestamp` for reproducible output.
- `ovrin harnesses` to print the loading matrix.
- Survey instrument: frozen-seed sampler, crawler, per-stratum analyzer.
