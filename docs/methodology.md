# Survey methodology

The measurement that accompanies this tool. Written down first, so the analysis
cannot drift toward whatever produces the better slide.

## The rule that governs everything

The sample is drawn once, by `survey/sample.py`, using a committed PRNG seed and
a candidate frame whose checksum is recorded, so the draw is genuinely random
and reproducible rather than the first N search results. `survey/crawl.py` reads
that sample and never re-draws. It walks each repository's tree recursively and
tests every instruction path against the repository's real CODEOWNERS file,
using the same matcher the scanner uses. The
submission is written from the results. We do not write a number and then go
looking for it.

## Questions

- Prevalence. How common are instruction files across active public repositories, and which formats dominate?
- Review coverage. What fraction sit outside CODEOWNERS, and how often is the file first added by an author's first commit to the repo?
- the carriage study Third-party origin. How many repositories would resolve a tree containing an instruction file they did not author, and under which agent rules would it become reachable?
- Loading behaviour. Which agents load which paths, at what precedence, and where do the boundaries disagree?

## Sampling

Stratified, to avoid a popularity-only bias.

| Stratum | Frame | Purpose |
| --- | --- | --- |
| A, top | Top repos by stars, per major language | Visibility-weighted picture |
| B, active | Reproducible random draw from a pre-defined active GitHub search frame (forks, archived, mirrors, templates excluded), pushed in the last 90 days from the snapshot date, at least 10 stars | An equal-weight stratified estimate, NOT an unbiased base rate of all GitHub |
| C, has-file | Repos already containing an instruction file | Review-coverage and authorship depth |

Target n around 5,000 for headline figures. Report per stratum. Never pool
without saying so. The minimum for a first defensible number is stratum B at
n=500, which is one afternoon with a token.

## What we collect

Per repository: presence and paths of instruction files, file size, CODEOWNERS
presence and whether it matches those paths, and per-file commit history so
authorship can be analysed.

## the carriage study without overclaiming

We do not claim every dependency-shipped file reaches an agent. We resolve
dependencies into a clean tree without running install scripts, locate any
instruction files, evaluate each agent's discovery and ignore rules, and report
counts per verdict with `unverified` kept separate from `loaded`. A result of
zero `loaded` third-party cases today is publishable. It is not a reason to
loosen the criteria.

## Ethics

- Benign canaries only. A marker file, a fixed string, a loopback request. Never credentials, never a real network destination.
- No pull requests against repositories we do not own. Third-party behaviour is read from public metadata.
- No repository named as vulnerable without contacting the maintainer first.
- Aggregate publication. Per-repo findings stay private.
- Anything resembling an agent flaw goes to the vendor before it goes on a slide.

## Threats to validity

- Public repositories only. Enterprise practice may differ.
- Agent behaviour is a moving target. Every matrix row is dated. Re-run before presenting.
- CODEOWNERS coverage is a proxy for review, not proof of it. Branch protection is incomplete over the public API.
- Package resolution is ecosystem-specific. npm resolves well, others less so. Report per-ecosystem coverage.
- GitHub only. GitLab, Gitea, and Codeberg are unmeasured.

## What the numbers are, and are not

- The sample is a reproducible random draw from a GitHub search frame of up to
  1,000 candidates per query, not a draw from all of GitHub. Report it as an
  equal-weight stratified estimate, never as an unbiased base rate.
- Forks, archived repositories, mirrors, and templates are excluded, because a
  fork carries its parent's files and would distort prevalence.
- Primary prevalence counts only auto-loaded formats (native, configurable,
  legacy). Manually loaded files such as aider's CONVENTIONS.md are reported
  separately, because the agent reads them only when explicitly told to.
- A truncated repository tree is never counted as a clean negative; it is
  excluded from the denominator.
- Per-language results are reported per language. Combining them is an
  equal-weight stratified estimate and is labelled as such.
- the carriage study covers only npm and Go, the ecosystems that materialise a scannable
  dependency tree under the repository. Each carried file is run through the
  real reachability engine, so the carriage study reports per-harness verdicts, not carriage
  alone.
- the resolution experiments records a created canary as loaded, and a missing canary as behaviour
  not-observed with loading unverified, never not-loaded. Confidence is recorded
  per behavioural claim, and one observed case promotes only that claim.
