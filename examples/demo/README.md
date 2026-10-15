# Ovrin 2-minute demo

A self-contained walkthrough for an Arsenal station or a quick local try.

```
pip install ".[sign]"      # from the repo root
bash examples/demo/demo.sh
```

It builds a throwaway repo (`/tmp/ovrin-demo`) seeded with a realistic
supply-chain layout — first-party instruction files, a **vendored** third-party
`CLAUDE.md` nobody on the repo reviewed, an installed npm dependency carrying
`AGENTS.md`, and an instruction file slipped in by a drive-by "add setup notes"
commit — then runs the five-beat story:

1. **Scan** — one line per instruction file: origin, review coverage, which agents load it.
2. **CI gate** — `--fail-on-third-party` exits non-zero on the vendored/`node_modules` rows.
3. **SPDX** — emit the provenance manifest as an SBOM-aligned artifact.
4. **Enforce** — a deny-by-default delegation policy blocks the undelegated vendored file (A_h=1, D=0).
5. **Sign** — produce and verify an Ed25519 signature over the manifest.

All instruction bodies are benign canaries; nothing here is an exploit.
