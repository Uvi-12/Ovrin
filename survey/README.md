# Survey

Measures, across a frozen and reproducible sample of public repositories, how
common agent configuration is and how much of it is third-party or outside
enforced review. Two surveys share the same sampler and the same CODEOWNERS
matcher the scanner uses:

- **Instruction files** (`AGENTS.md`, `CLAUDE.md`, and the rest) — `crawl.py` + `analyze.py`.
- **Executing configuration** (MCP servers in `.mcp.json`, hooks in `.claude/settings.json`, skills) — `crawl_exec.py` + `analyze_exec.py`.

Everything here uses the GitHub API only. It is read-only, honours rate limits,
and opens no pull requests against repositories you do not own.

## Install

```
pip install ".[survey]"
export GITHUB_TOKEN=...        # a token with public-repo read access
```

## Run the execution survey

The orchestrator runs the whole protocol in `protocol.yaml` — it draws each
sample once, crawls it, and analyses the results together:

```
python survey/run_sweep.py                 # full protocol
python survey/run_sweep.py --dry-run        # show the plan without touching anything
```

It is resumable. Each sample is frozen on first draw and never redrawn; if the
API rate limit pauses a crawl, run the same command again and it continues from
where it stopped. Outputs land in `survey/out/`:

- `report-exec.txt` and `analysis-exec.json` — the numbers, per stratum, with confidence intervals;
- `sample-*.json` — the frozen samples (seed, query, frame checksum);
- `manifest.json` — snapshot date, seeds, and tool versions.

## Run the instruction survey

```
python survey/sample.py  --stratum active --language python --snapshot 2026-10-31 \
    --window-days 90 --n 500 --seed 20261031 --out survey/out/sample-active-python.json
python survey/crawl.py   --sample survey/out/sample-active-python.json \
    --out survey/out/records-active-python.jsonl --history
python survey/analyze.py survey/out/records-active-python.jsonl --json-out survey/out/analysis.json
```

## Reproducibility

Commit the frozen samples, the records, and the manifest alongside your results.
The sampling protocol is documented in [../docs/methodology.md](../docs/methodology.md).
Report per stratum and language; do not pool across them without treating it as
an equal-weight stratified estimate.
