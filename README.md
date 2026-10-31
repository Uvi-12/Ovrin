# Ovrin

**Know which configuration files your coding agent reads and runs — where each one came from, whether anyone reviewed it, and which agents will act on it.**

![Version](https://img.shields.io/badge/version-0.1.0-6D4AFF)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)

---

## What this is

Coding agents such as Claude Code, Codex, Cursor, and Gemini CLI read files in a
repository as configuration and act on them. Some of those files only shape what
the agent intends (`AGENTS.md`, `CLAUDE.md`, `.cursorrules`). Others cause code to
run when the agent starts — an MCP server definition in `.mcp.json`, a hook in
`.claude/settings.json`. Either way, the file can enter a repository through a
pull request that looks like documentation, or ride in on a dependency nobody
read, and it sits outside the tooling teams already use to review code.

Ovrin inventories those files and tells you, for each one:

- **where it came from** — written by the team, vendored in, or pulled in by a dependency;
- **whether review is actually enforced on it** — not just that a `CODEOWNERS` line matches the path, but that it requires an approval;
- **which agents will load it**, and, for configuration that runs code, **what it can do**: spawn a process, reach the network, reference a credential, run an unpinned package, or run code that lives inside a dependency.

It then turns that inventory into a build gate you can run in CI, an
SBOM-aligned manifest, and a signed, tamper-evident record.

The scanner runs offline and makes no network calls.

## Install

```
git clone https://github.com/Uvi-12/ovrin
cd ovrin
pip install .
```

Optional extras: `pip install ".[sign]"` adds manifest signing; `pip install ".[survey]"`
adds the ecosystem-measurement tools (described below).

## Scan a repository

```
ovrin scan .
```

```
Agent configuration manifest
  subject      /work/example
  codeowners   .github/CODEOWNERS
  rules        harnesses v0.1.0 (matrix dated 2026-08-11, documented)
               executing config v0.2.0 (dated 2026-10-31; see `ovrin harnesses`)

Instruction files
  PATH                             ORIGIN                REVIEW       LOADED BY
  CLAUDE.md                        repo                  enforced?    claude-code
  docs/onboarding/AGENTS.md        repo                  enforced?    codex-cli,cursor,devin-desktop
  node_modules/left-pad/AGENTS.md  installed-dependency  no           - (?codex-cli,cursor,devin-desktop)
  packages/api/AGENTS.md           repo                  enforced?    codex-cli,cursor,devin-desktop
  vendor/telemetry-kit/CLAUDE.md   vendored              enforced?    claude-code

Executing configuration
  PATH                            ORIGIN                REVIEW       LOADED BY               CAN
  .claude/settings.json           repo                  enforced?    claude-code             exec
  .mcp.json                       repo                  enforced?    claude-code             exec
  vendor/telemetry-kit/.mcp.json  vendored              enforced?    - (not at root)         exec

  BLOCK  .claude/settings.json: runs vendored code at vendor/telemetry-kit/setup.sh, outside the project's own reviewed source
  warn   vendor/telemetry-kit/.mcp.json: vendored executing configuration; loaded only if an agent is launched in vendor/telemetry-kit
  Not repository-local: codex-cli (executing config is global, so a committed file cannot inject it).

Summary
  instruction files    5
  third-party origin   2
  not review-enforced  5
  first commit by author  4
  git-ignored path     1
  executing config     3  (loaded at root 2, can run code 3)
  runs third-party code  1
  exec-risk findings   1 blocking

  '?' marks a harness whose behaviour we have not verified.
  See docs/loading-matrix.md before citing any verdict.
```

The third-party rows are the point: neither file was written by this project.
The `BLOCK` line is the sharper case. The hook in `.claude/settings.json` sits at
the root, where Claude Code loads it on every session, and it runs a script that
lives inside a vendored package. The vendored package's own `.mcp.json` is only
a warning, because an agent launched at the root does not load it; the
activation benchmark recorded buried configuration executing in none of its
trials.

Other output formats and the full manifest:

```
ovrin scan . -f json -o manifest.json        # full provenance manifest
ovrin scan . -f spdx -o manifest.spdx.json   # SPDX 3.0, sits beside your SBOM
ovrin harnesses                              # which agent loads which files, and how confident we are
```

## Gate a pull request

Fail the build when configuration arrives without review or from a dependency:

```
ovrin scan . --fail-on-unreviewed     # exit 1 if any instruction file has no enforced review
ovrin scan . --fail-on-third-party    # exit 1 if any instruction file came from a dependency or submodule
ovrin scan . --fail-on-exec-risk      # exit 1 if executing config loaded at the root runs
                                      # code with no enforced review, or runs dependency code
```

`--fail-on-exec-risk` blocks only what an agent would actually run: a `.mcp.json`
server, a `.claude/settings.json` or `.gemini/settings.json` hook, at the
repository root, that either has no enforced review or executes a path inside a
vendored or installed dependency. Executing configuration buried in a
dependency, unpinned package versions, and skills (which the model, not the
harness, decides to run) are reported as warnings and never fail the build.

Apply a delegation policy (which sources may govern which paths) and emit SARIF
for code scanning:

```
ovrin enforce . --policy policy.yaml -f sarif -o ovrin.sarif
```

Sign a manifest so a reviewer with only the public key can confirm it was not altered:

```
ovrin keygen --out-dir .ovrin-keys
ovrin scan . -f json -o manifest.json
ovrin sign manifest.json --key .ovrin-keys/ovrin-signing.key -o manifest.json.sig
ovrin verify manifest.json --sig manifest.json.sig --pub .ovrin-keys/ovrin-signing.pub
```

A full run on a small example repository:

```
bash examples/example-project/run-ovrin.sh
```

## Repository layout

```
src/ovrin/          The scanner, the gate, provenance and review classification,
                    SPDX output, and manifest signing. This is the tool.
tests/              Test suite for the tool.
survey/             Ecosystem measurement over public repositories:
                    how common agent configuration is, and how much of it is
                    third-party or unreviewed. Instruction files and executing
                    configuration (MCP servers, hooks) are measured the same way.
research/
  activation/       A reproducible harness that measures, against real agents,
                    whether a repository's configuration is executed when the
                    agent opens the repository.
  ...               Supporting studies and reproducibility material.
examples/           An example repository and a script that runs the tool on it.
docs/               Method, threat model, manifest specification, and the
                    agent loading matrix.
```

## Research components

Two measurement tools ship with the tool. Both are read-only and reproducible,
and both are optional — the scanner does not depend on them.

### Ecosystem survey (`survey/`)

Measures, across a frozen, reproducible sample of public repositories, how common
agent configuration is and how much of it is third-party or outside enforced
review. It uses the GitHub API only.

```
pip install ".[survey]"
export GITHUB_TOKEN=...                 # a token with public-repo read access

python survey/run_sweep.py              # runs the full protocol in survey/protocol.yaml
```

The run is resumable: it freezes each sample once, continues where it stopped if
the API rate limit pauses it, and writes a report, a machine-readable analysis,
and a manifest that records the sample seeds and tool versions. See
[`survey/README.md`](survey/README.md).

### Activation benchmark (`research/activation/`)

Measures whether a repository's configuration is executed when a real agent
opens the repository, across agents and dependency depth, using inert markers
only. Runs against a built-in mock agent out of the box, so you can see the
whole pipeline before connecting a real one.

```
cd research/activation
./run.sh                                # self-test with the built-in mock agent
```

To run it against a real agent, enable that agent in `config.yaml` and follow
[`research/activation/README.md`](research/activation/README.md).

## Documentation

- [`docs/methodology.md`](docs/methodology.md) — how the survey is sampled and analysed
- [`docs/threat-model.md`](docs/threat-model.md) — what Ovrin defends against, and what it does not
- [`docs/origin-classification.md`](docs/origin-classification.md) — how provenance is decided
- [`docs/loading-matrix.md`](docs/loading-matrix.md) — which agent loads which files, and the confidence behind each verdict
- [`docs/manifest-spec.md`](docs/manifest-spec.md) and [`docs/spdx-mapping.md`](docs/spdx-mapping.md) — the manifest and its SBOM mapping

## Status and license

Alpha. The scanner and its tests are stable; interfaces may still change.
Apache-2.0. See [`LICENSE`](LICENSE), [`SECURITY.md`](SECURITY.md), and
[`CONTRIBUTING.md`](CONTRIBUTING.md).
