# the carriage study methodology: third-party carriage, provenance, and conditional reachability

## Question

To what extent do third-party software carriers introduce coding-agent
instruction artifacts into developer workspaces; what verifiable provenance
links each artifact to a specific external package or source; and under what
documented discovery, path, workspace, and ignore conditions is that artifact
eligible to enter an agent's instruction context?

the carriage study proves: origin -> carrier -> materialization -> governance -> conditional
reachability. the carriage study never asserts that an agent loaded an instruction; that is
the resolution experiments. the carriage study verdicts are structural eligibility only.

## Inputs

The frozen RQ1/RQ2 samples (seed 20260811, snapshot 2026-08-11, activity cutoff
2026-05-13). No resampling. the carriage study recrawls dependency state for the same repos.

## Pinned toolchains (reproducibility anchor)

All resolution runs inside throwaway containers. The host machine installs no
language toolchain. Versions are pinned by image:

| Ecosystem  | Image                             | Tool version   |
| ---------- | --------------------------------- | -------------- |
| Go         | golang:1.23                       | go 1.23.12     |
| JavaScript | node:22                           | npm 10.9.8     |
| Rust       | rust:1.83                         | cargo 1.83.0   |
| Python     | python:3.13                       | python 3.13.15 |
| Java       | maven:3.9-eclipse-temurin-21      | maven 3.9.16   |

## Safe materialization (no dependency code execution)

Each ecosystem uses a resolve command that materializes dependency files
WITHOUT executing package lifecycle, build, or application code:

| Ecosystem  | Command                                              | Why it is safe                          |
| ---------- | ---------------------------------------------------- | --------------------------------------- |
| Go         | committed vendor/ (on disk after clone) or go mod vendor | vendoring copies files, runs no pkg code |
| JavaScript | npm ci --ignore-scripts                              | frozen install, lifecycle scripts off   |
| Rust       | cargo vendor --locked                                | uses locked resolution, copies sources  |
| Python     | pip download --only-binary=:all: then isolated unpack | downloads wheels, no sdist build, no import |
| Java       | mvn dependency:go-offline                            | resolves archives to cache, no build    |

Container safety properties, every run: source copied to a writable work dir
(original clone never mutated); network restricted to the package registry;
--ignore-scripts / --locked / --only-binary where applicable; container is --rm
(throwaway); resource/time caps applied.

## Origin confidence (headline uses PROVEN only)

Path name alone (vendor/, node_modules/, site-packages/) NEVER establishes
third-party origin; it only identifies a candidate.

| Confidence | Meaning                                                       | Headline  |
| ---------- | ------------------------------------------------------------ | --------- |
| PROVEN     | Exact external package/version/source mapped to the artifact | yes       |
| STRONG     | External source established, package mapping incomplete      | secondary |
| HEURISTIC  | Looks third-party by directory/path convention only          | no        |
| UNKNOWN    | Origin cannot be established                                  | no        |

Provenance anchors: Go = vendor/modules.txt; npm = package-lock resolved +
integrity; Rust = Cargo.lock + vendored .cargo-checksum.json; Python = wheel
RECORD/METADATA; Java = Maven coordinates.

## Carrier classes (reported separately, never pooled)

- repository-carried: artifact already present in the checkout (committed
  vendor/, submodule). Present immediately after git clone; no package manager
  runs. Strongest no-code-execution case.
- resolver-carried: artifact placed on disk by a normal resolution/materialize
  step (node_modules/, site-packages/, cargo vendor output).
- archive-contained: artifact exists inside a dependency archive (Java JAR) but
  is NOT loose in the tree where a file-walking agent would meet it. Negative /
  boundary control.

Monorepo workspace components are NOT third-party unless separate provenance
proves external origin; otherwise workspace-first-party or workspace-unknown,
excluded from the third-party headline.

## Governance intersection

For each PROVEN artifact record independently: tracked by git? ignored by git?
inside the host repo? host CODEOWNERS syntactically covers the path? carrier
identified by manifest/lockfile? integrity available?

## Conditional reachability (structural eligibility, not loading)

Each PROVEN artifact is evaluated by the CWD-aware reachability engine under at
least two concrete task contexts, never with an unspecified working directory:

- host-task: agent works on ordinary first-party source (active path in src/).
- carrier-task: agent works inside the dependency subtree (active path in the
  carrier directory).

Verdicts: DOCUMENTED_REACHABLE, DOCUMENTED_EXCLUDED, CONDITIONALLY_REACHABLE,
NOT_APPLICABLE, UNVERIFIED. Never LOADED. Confidence per verdict: DOCUMENTED
(vendor docs), SOURCE-VERIFIED (OSS harness code), UNKNOWN. OBSERVED is reserved
for the resolution experiments.

The distinction that matters most: host-task reachability (artifact can enter
context during ordinary first-party work) vs carrier-local reachability (only
when the agent is already inside the dependency).

## Denominator ladder (report every rung; never hide failures)

    usable sampled repositories
      -> repositories with a dependency manifest
        -> repositories with deterministic/resolvable dependency state
          -> resolution attempts that succeeded safely
            -> repositories materializing >=1 PROVEN third-party instruction
              -> repositories with >=1 conditionally reachable such instruction
                -> repositories where third-party origin + governance gap +
                   conditional reachability intersect (W)

Every resolution failure is retained with a reason (build-required, network,
manifest-invalid, no-lockfile, timeout, ...). Rates are reported both over
successfully-resolved repos (the package-manager phenomenon) and over all usable
sampled repos (population impact), each labelled.

## Ecosystems are not forced into identical procedures

Native evidence per ecosystem is used. Three ecosystems are expected to give
loose-file carriage (Go, npm, Rust); Python is conservative (wheels only, no
sdist builds); Java is expected to be archive-contained (negative/boundary
control). A smaller, clean, PROVEN denominator is preferred over a larger
heuristic one.

## Headline outputs

Six numbers: safely-resolved N; carriage X/N; PROVEN artifacts M; no-code-
execution carriage Y/N; conditionally-reachable Z/N; intersection W/N. Plus the
host-task vs carrier-local split among W. Equal-weight stratified across five
languages, labelled as such, never silently pooled.