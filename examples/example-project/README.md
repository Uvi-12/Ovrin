# Example project

A small repository you can build locally to see what Ovrin reports and how the
CI gate, the SPDX manifest, policy enforcement, and manifest signing behave.

## How to run

From the repository root, with Ovrin installed (`pip install ".[sign]"`):

```
bash examples/example-project/run-ovrin.sh
```

This creates a throwaway project under `/tmp/ovrin-example` containing a mix of
configuration files — first-party ones, a configuration file carried in by a
vendored dependency, one carried in by an installed package, and a later commit
by a different author that adds setup notes and a `.claude/settings.json` hook
running a script inside the vendored package — and then runs Ovrin on it end to end:

1. **Scan** — one line per file: where it came from, whether review is enforced, which agents would load it, and, for executing configuration, what it can do.
2. **Instruction gate** — `--fail-on-third-party` exits non-zero when an instruction file arrived from a dependency.
3. **Execution gate** — `--fail-on-exec-risk` exits non-zero because the root hook runs vendored code.
4. **SPDX** — writes the provenance manifest in SPDX 3.0 form, to sit beside an existing SBOM.
5. **Enforce** — applies the deny-by-default policy in `authority-policy.yaml` and blocks the undelegated file.
6. **Sign and verify** — produces an Ed25519 signature over the manifest and verifies it.

Every file body is a harmless marker. The hook script only writes a marker file,
and Ovrin never runs it: the scanner reads configuration as data.
