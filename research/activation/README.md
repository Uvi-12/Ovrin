# Activation benchmark

Measures whether a repository's configuration is **executed** when a real coding
agent opens the repository — not whether the agent is told to do something, but
whether a configuration file carried in the repository causes code to run on its
own. It runs across agents and across dependency depth, and every payload is an
inert marker: a file that records that it ran, a throwaway secret, a sentinel
line in a throwaway workflow. Nothing touches real systems.

## What it reports

For each agent and each placement of the configuration, the share of runs in
which the configuration executed, with 95% confidence intervals:

- **root** — a configuration file at the repository root.
- **vendored** / **transitive** — the same file inside a dependency, one or several levels deep.
- **exec-vendored** — a configuration file at the reviewed root whose command runs code vendored inside a dependency.

It also measures a consequence matrix (does the executed code read a throwaway
secret, or disable a throwaway CI check?) and validates the Ovrin gate against
the same cases (precision, recall, and whether the gate would have blocked what
actually ran).

## How to run

Out of the box it runs against a built-in mock agent, so you can see the whole
pipeline — samples, execution, analysis, report, and a draft disclosure — before
connecting anything real:

```
./run.sh
```

Results are written under `results/`, with a `report.md` and a `manifest.json`
that records the agent versions, the corpus hash, and the trial count.

### Running against a real agent

1. Install and sign in to the agent's CLI (for subscription agents this is a
   login, not an API key).
2. In `config.yaml`, set that agent's `enabled: true`.
3. Run `./run.sh`. If the agent pauses on a usage limit, `./resume.sh` continues
   from where it stopped — every trial is checkpointed.

To run several agents at once without their results colliding, give each its own
run:

```
./run.sh --agents claude-code --run-id claude
./run.sh --agents gemini      --run-id gemini
```

## Scope and safety

Run this only against throwaway repositories you own. Payloads are inert markers;
the harness performs no real credential access, exfiltration, or code execution
against third-party systems. If a run shows a real agent executing repository
configuration, disclose it to that vendor before publishing. A draft disclosure
is generated under `results/disclosure/` for any agent that showed activation.
