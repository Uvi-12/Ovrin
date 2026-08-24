# Research

This directory contains the empirical study behind Ovrin: how coding-agent
instruction files are carried into repositories, whether they are governed, and
how each agent harness resolves *which* instruction actually reaches the model
at runtime.

The tool in `src/ovrin` is the product. This directory is the evidence.

## Layout

- **`carriage-study/`** — prevalence and provenance of agent instruction files
  across real repositories (five ecosystems). Measures how often third-party
  carriers introduce instruction files and how often those files are governed.
  Results in `carriage-study/results/`.

- **`harness-matrix/`** — per-harness resolution experiments. Each script
  isolates one mechanism by which the *effective* instruction can differ from
  the *reviewed* one:
  - `import_carriage.py` — instruction authority crossing a dependency boundary
    through an import directive (Claude Code `@import`).
  - `precedence.py`, `scoped_precedence.py` — which file wins when several are
    in scope.
  - `discovery_gemini.py`, `nested_discovery_*.py` — root-to-cwd and nested
    discovery behaviour.
  - `dependency_depth.py` — how directory depth maps to precedence position.
  - `read_triggered_activation.py` — just-in-time activation on file access.
  - `workspace_trust_classification.py` — whether the trust boundary tracks
    filesystem containment or provenance.
  - `version_rebinding.py` — authority rebinding when an imported file changes.
  - `bound_autonomous.py`, `bound_saferule.py` — control conditions bounding the
    effect (no autonomous takeover; restriction-style rules resist).
  - `authority_divergence.py` — the combined reviewed-vs-effective divergence
    measurement across mechanisms, with confidence intervals and a prediction
    loop using the shipped resolver.
  - `combined_runner.py`, `survey_runner.py` — batch runners.

- **`reachability/`** — the resolver logic that predicts the effective
  instruction for a given repository and harness.

- **`reproducibility/`** — scripts to reproduce the study.

- **`RESULTS.md`** — consolidated findings. Retains the original research
  question labels (prevalence, governance gap, and the per-mechanism results)
  as a lab record.

## Method note

All experiments use benign sentinel markers (a token in a docstring), never a
harmful action. The finding is that governance operates on the file while the
harness resolves authority at runtime — delegation resolved at the wrong layer,
not an exploit. Rates are proportions over N trials with Wilson 95% confidence
intervals; a divergence counts only as the bracketed difference from its own
control.
