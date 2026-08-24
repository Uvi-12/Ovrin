# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-08

### Added
- `ovrin scan` with table, JSON, and SPDX 3.0-aligned output.
- Origin classification: repo, workspace, submodule, vendored, installed-dependency, untracked.
- The `vendored` versus `installed-dependency` split, so a committed vendor tree and an installed package are not counted the same.
- CODEOWNERS resolution with last-match-wins, and a `ruleMatches` versus `enforceable` split so a catch-all rule is not reported as review.
- Per-agent reachability with explicit confidence levels and an `unverified` verdict.
- `authoredInFirstPR`, whether an instruction file was first added by an author's first commit to the repo.
- Complete-or-absent digests. A partial hash is never emitted.
- `--no-timestamp` for reproducible output.
- `ovrin harnesses` to print the loading matrix.
- Survey instrument: frozen-seed sampler, crawler, per-stratum analyzer.
