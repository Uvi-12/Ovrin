# How to generate the research numbers

Everything here runs on your machine, not in any sandbox. The scanner and the
analysis are already tested. These are the four network-dependent steps that
produce the real numbers for the abstract.

You need: Python 3.10+, a `GITHUB_TOKEN` with public-repo read scope, and for
the carriage study a container runtime or a throwaway VM.

## 0. Install

```
pip install -e ".[survey,dev]"
export GITHUB_TOKEN=ghp_your_token_here
```

## 1. RQ1 + RQ2: the survey (this gives you the CODEOWNERS headline)

Files: `survey/sample.py`, `survey/crawl.py`, `survey/analyze.py`

```
# draw a genuinely random, reproducible sample (commit the output)
# smoke test today (disposable, do NOT use the numbers):
python survey/sample.py --stratum active --language python \
    --snapshot 2026-08-11 --window-days 90 --n 20 --seed 999001 \
    --out survey/out/SMOKE-sample.json
python survey/crawl.py --sample survey/out/SMOKE-sample.json \
    --out survey/out/SMOKE-records.jsonl
python survey/analyze.py survey/out/SMOKE-records.jsonl | tee survey/out/SMOKE-analysis.txt

# the real frozen sample: use the day you actually run it as the snapshot,
# and a seed derived from it, then commit the sample file.
python survey/sample.py --stratum active --language python \
    --snapshot 2026-08-11 --window-days 90 --n 500 --seed 20260811 \
    --out survey/out/sample-active-python.json

# crawl it: recursive tree walk + real CODEOWNERS path matching + history
python survey/crawl.py --sample survey/out/sample-active-python.json \
    --out survey/out/records-active-python.jsonl --history

# analyze: prevalence, coverage gap, Wilson CIs, bootstrap-by-repo
python survey/analyze.py survey/out/records-active-python.jsonl \
    --json-out survey/out/analysis-active-python.json
```

Repeat for other languages and for `--stratum top` and `--stratum hasfile`.
Commit every `survey/out/*.json` and `*.jsonl` so the numbers reproduce.

The number you want for the abstract comes out of RQ2:

> instruction files outside CODEOWNERS coverage: X/Y (Z%, 95% CI ...)

The first-commit-by-author metric is reported but should NOT be load-bearing in
the abstract; the CODEOWNERS gap is enough.

## 2. the resolution experiments: observe real harnesses (turns the matrix from documented to observed)

File: `research/harness-matrix/observe.py`

Install the agents you want to test (at least three open ones: Codex CLI,
Gemini CLI, and one of goose / Cline / Continue). Then, for each:

```
python research/harness-matrix/observe.py --agent codex-cli --case root-agents-md \
    --out tests/harness_cases/codex-cli/root-agents-md/RESULT.md
```

It builds a canary layout, prints the command to run, waits, and records whether
the agent loaded the instruction. Do this for the cases that matter:
`root-agents-md`, `nested-agents-md`, `ignored-node-modules`, `vendored-tree`,
and the marquee one, `override-precedence`.

For a case that comes back `loaded`, set `confidence: observed` ONLY on the
specific behavioural claim it tested (e.g. `root_loading`), in that harness's
`claims` block in `src/ovrin/data/harnesses.yaml`. One case does not make the
whole agent observed.

If `override-precedence` shows a subdirectory override nullifying a root safety
restriction, disclose to the vendor before it goes on a slide.

## 3. the carriage study: dependency-tree reachability (the supply-chain number)

File: `research/reachability/resolve.py`

Run this inside a container or throwaway VM. It never runs install scripts.

```
python research/reachability/resolve.py --repo owner/name --ecosystem npm \
    --out research/reachability/results/owner-name.json
```

Only npm and Go are supported, because only they materialise a scannable tree
under the repository. Each carried file is run through the real reachability
engine, so the result is per-harness verdicts, not just carriage. State it as
"the carriage study covers safely materialised npm and Go dependency trees."

## 4. Fill the five blanks, then write the abstract

Do not write the final abstract until these are real:

```
N   repositories measured
X%  instruction-file prevalence
Y%  files outside CODEOWNERS coverage      <- the headline
Z%  externally carried (the carriage study)
H harnesses, D% disagreement (the resolution experiments)
```

Then build the submission around whichever two or three turned out interesting.
