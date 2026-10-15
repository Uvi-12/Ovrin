# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `ovrin keygen` / `ovrin sign` / `ovrin verify`: Ed25519 detached signatures over the
  manifest's canonical bytes (optional `[sign]` extra). Asymmetric by design, so a
  verifier cannot forge a manifest.
- Composite GitHub Action (`action.yml`), a `.github/workflows/scan.yml`, a pre-commit
  hook (`.pre-commit-hooks.yaml`), and a VS Code task (`examples/editor/`).
- A self-contained 2-minute demo (`examples/demo/`): scan → gate → SPDX → enforce → sign.
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
