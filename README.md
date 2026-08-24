# OVRIN

**Inventory the instruction files your coding agent silently obeys: AGENTS.md, CLAUDE.md, GEMINI.md, .cursorrules, and the rest.**

![Version](https://img.shields.io/badge/version-0.1.0--alpha-6D4AFF)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)

---

## The problem, in one sentence

A coding agent reads files like `AGENTS.md` and `CLAUDE.md` as configuration and does what they say, but those files arrive through pull requests looking like documentation, sit outside the usual SBOM and lockfile tooling, and can be carried into your tree by a dependency you never read, so an instruction the agent obeys may be one nobody reviewed.

The audit trail shows a reviewed pull request. The instruction the agent followed may never have been in it.

The carrier does not need a stolen token, a prompt injection, or code execution. It needs only a Markdown file on a path the agent walks, which a vendored dependency, a submodule, or an ordinary "add setup notes" pull request can all provide.

## See it in 20 seconds

```
pip install ovrin
ovrin scan .
```

`ovrin scan` walks the repository and prints one line per instruction file: where it came from, whether review is enforced on it, and which agents would load it.

```
Agent instruction manifest
  subject      /work/example
  codeowners   .github/CODEOWNERS
  rules        harnesses v0.1.0 (verified 2026-08-11)

  PATH                             ORIGIN                REVIEW       LOADED BY
  .cursorrules                     repo                  enforced?    cursor
  AGENTS.md                        repo                  enforced?    codex-cli,cursor,copilot,devin-desktop,amp
  CLAUDE.md                        repo                  enforced?    claude-code
  node_modules/left-pad/AGENTS.md  installed-dependency  no           - (?codex-cli,cursor,devin-desktop,amp)
  packages/api/AGENTS.md           repo                  enforced?    codex-cli,cursor,devin-desktop,amp
  vendor/acme/CLAUDE.md            vendored              enforced?    claude-code

Summary
  instruction files    6
  third-party origin   2
  not review-enforced  6
  first commit by author  5
  git-ignored path     1
```

The two third-party rows are the point. Neither file was written by this project. The `node_modules` one is git-ignored, so whether an agent reads it depends on that agent's ignore behaviour, which is why it reads `?codex-cli` and not a flat verdict. The `vendor/` one is committed, so ignore rules do not help; it stays within the discovery scope of any agent whose documented rules walk that part of the tree, and Ovrin keeps the verdict `unverified` wherever loading has not been observed.

## Install

```
pip install ovrin
```

That is the whole install. The scanner runs offline and makes no network calls. The optional survey tools pull one extra:

```
pip install "ovrin[survey]"
```

## Use it on your own project

```
ovrin scan .                       # the table above
ovrin scan . -f json -o out.json   # the full instruction provenance manifest
ovrin scan . -f spdx -o out.spdx.json   # SPDX 3.0-aligned, sits beside your SBOM
ovrin harnesses                    # the loading matrix and its confidence levels
```

Gate a pull request in CI:

```
ovrin scan . --fail-on-unreviewed    # exit 1 if any instruction file has no enforced review
ovrin scan . --fail-on-third-party   # exit 1 if any arrived from a dependency or submodule
```

A drop-in GitHub Actions workflow is in [`.github/workflows/scan.yml`](.github/workflows/scan.yml).

## What the manifest records

For each instruction file:

| Field | What it means |
| --- | --- |
| `origin.class` | `repo`, `workspace`, `submodule`, `vendored`, `installed-dependency`, `untracked` |
| `origin.package` | Resolved `name@version` where the ecosystem allows it |
| `review.ruleMatches` | A CODEOWNERS rule syntactically matches this path |
| `review.enforceable` | `false` for ignored or untracked paths, `null` when it depends on branch protection |
| `introducedInAuthorsFirstCommit` | The file's first commit is also that author's earliest in the repo (a git fact, not a PR claim) |
| `digest` | SHA-256 of the complete file, or `null` — never a hash of part of a file |
| `reachability` | Per agent: `loaded`, `ignored`, `not-discovered`, or `unverified` |

Full schema: [`docs/manifest-spec.md`](docs/manifest-spec.md).

## On the "loaded by" column

Agents differ, and the differences decide everything. Some walk the whole tree, some read only the repository root, some walk upward past it, and at least one respects ignore rules, which means it never reads `node_modules` at all.

Ovrin does not assume they behave the same. Where a harness's behaviour has not been verified, the verdict is `unverified` and the table prints `?`. Every row in [`docs/loading-matrix.md`](docs/loading-matrix.md) carries a confidence level, and only rows marked `observed` have actually been run against the real agent. The rest are `documented` or `inferred`, and correcting them is the most useful contribution you can make.

## Why SPDX

It is a software artifact, and it belongs in the same bill of materials as everything else. Conventional SBOM generators enumerate packages and miss these loose files, and the inventory tools that have begun to catalogue them (such as agent-bom) do not answer Ovrin's review-coverage, provenance, and reachability questions. The SPDX exporter writes each instruction file as a `software_File` with its digest, origin, and reachability, so those measurements can sit next to a conventional SBOM instead of in a separate silo. Output is SPDX 3.0-aligned; see [`docs/spdx-mapping.md`](docs/spdx-mapping.md) for what "aligned" means and what still needs the official validator.

## Is this real? The prior work

The attack this inventories is not hypothetical. Poisoned agent rules files were demonstrated as a supply chain attack by Pillar Security in 2025, and instruction-file injection has since been documented by NVIDIA, Microsoft, and Aikido. Ovrin is not a rediscovery of that attack. Adjacent tooling has begun to appear: agent-bom inventories instruction artifacts such as CLAUDE.md, .cursorrules and AGENTS.md. Ovrin's contribution is narrower and deeper: ecosystem-scale review-control measurement, origin attribution, carrier provenance, and cross-agent conditional reachability.

Full account with sources: [`docs/related-work.md`](docs/related-work.md).

## What this is not

- Not a content scanner. Ovrin records what exists and where it came from. It makes no judgement about what a file says. Deciding whether an instruction is malicious is a person's job.
- Not an agent sandbox or a runtime guard.
- Not a claim that any agent is vulnerable. The matrix records behaviour, including the agents that behave conservatively.

## Documentation

- [What an instruction file is, and why it is a dependency](docs/threat-model.md)
- [The loading matrix](docs/loading-matrix.md)
- [Manifest schema](docs/manifest-spec.md)
- [SPDX mapping](docs/spdx-mapping.md)
- [Origin classification](docs/origin-classification.md)
- [Survey methodology](docs/methodology.md)
- [Related work](docs/related-work.md)
- [Limitations](docs/limitations.md)

## Contributing

The most useful contribution is a harness reproduction: run an agent, watch what it loads, and turn a `documented` row into an `observed` one. See [CONTRIBUTING.md](CONTRIBUTING.md). Please report security issues in Ovrin itself privately, see [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

## Citation

If you build on this work, please cite it. See [CITATION.cff](CITATION.cff).
