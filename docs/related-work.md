# Related work

Ovrin is not a rediscovery of instruction-file injection. That attack is
established. This project addresses the inventory and provenance problem that
follows from it.

## The attack is known

- Pillar Security (2025) described the Rules File Backdoor: malicious instructions hidden in coding-agent rules files, distributed through repositories, framed explicitly as a software supply chain attack against Cursor and GitHub Copilot.
- NVIDIA (2026) documented indirect `AGENTS.md` injection in agentic development environments. Their own caveat is that the chain presupposes a compromised dependency, which already implies code execution.
- Microsoft Security (2026) published on prompt injection reaching coding agents through CI, including a Claude Code Action case.
- Aikido (2026) disclosed a pattern across several agents running in GitHub Actions and GitLab CI.

## The ecosystem is already studied

- Work evaluating whether `AGENTS.md` files help coding agents.
- A configuration-smell taxonomy derived from open-source repositories.
- Work converting instruction files into executable checks.
- Work on poisoned agent skills.
- GitHub analysed more than 2,500 repositories with `AGENTS.md` and concluded most fail because they are too vague.

So raw prevalence is not novel. "We found thousands of these files" is not a finding.

## Adjacent tooling

- agent-bom (PyPI) audits instruction artifacts such as `CLAUDE.md`, `.cursorrules`, `AGENTS.md` and `SKILL.md`. It inventories these files. Ovrin's research contribution is the layer agent-bom does not cover: review-control coverage measured at ecosystem scale, origin attribution with evidence, carrier provenance through dependency trees, and harness-dependent reachability.

## What we could not find prior work on

1. Review-control coverage. Whether these paths fall under CODEOWNERS or branch protection at all, at ecosystem scale.
2. Origin attribution. Repository-authored versus submodule, vendored tree, workspace member, or installed dependency, with evidence.
3. A cross-agent discovery matrix with stated confidence levels.
4. An inventory artifact a maintainer can generate, diff, and attach to an SBOM.

Those four are what Ovrin produces. If you know of prior work covering any of them, please open an issue. We would rather cite it than duplicate it.
