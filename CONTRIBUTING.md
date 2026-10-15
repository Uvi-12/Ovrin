# Contributing to Ovrin

Thanks for helping make agent instructions something a project can actually see.

## Getting set up

```
git clone https://github.com/Uvi-12/ovrin
cd ovrin
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## The most useful contribution

A harness reproduction. The loading matrix in `docs/loading-matrix.md` claims
things about how agents discover instruction files, and several rows are
`documented` or `inferred`, which means nobody has run the agent and watched.

To turn a row into `observed`:

1. Add a case under `tests/harness_cases/<agent-id>/`, with the directory layout, any ignore files, and a benign canary instruction.
2. Run the agent. The canary must be inert: write a marker file, emit a fixed string. Never credentials, never a real network destination.
3. Record what happened in `RESULT.md`: agent version, command, whether the instruction was acted on, how you confirmed it.
4. Set `confidence: observed` in `data/harnesses.yaml` with a source pointing at your case.

We hold this line strictly, because the matrix is presented as research. An
unearned `observed` is worse than an honest `documented`.

## Adding an agent or a format

Open a pull request adding an entry to `data/harnesses.yaml` or
`data/formats.yaml` with `confidence: unknown` and a source. Listing an agent we
have not tested is fine. Claiming we tested it is not.

## Before you open a pull request

- Run `pytest` and `ruff check .`.
- Keep the scanner honest: when it cannot decide something, it reports `unverified` or `unknown`. Do not add heuristics that guess.
- No `print` debugging left in.
- Digests stay complete or absent. Never emit a hash of part of a file.

## Reporting security issues

Please do not open a public issue for a vulnerability in Ovrin itself, or
for an unpatched agent flaw you found while using it. See [SECURITY.md](SECURITY.md).
