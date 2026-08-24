# What an instruction file is, and why it is a dependency

An instruction file is a file a coding agent reads as configuration and acts on:
`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, and their kin. It tells
the agent how to build, test, and behave, and a capable agent follows it.

It has every property of a dependency:

- Executable in effect. The agent does what it says.
- Transitively inherited. A dependency, submodule, or workspace member can ship one into your tree.
- Mutable without notice. A pull request can add or change one.

And none of the controls:

- No lockfile entry, no version pin.
- No signature, no provenance attestation.
- No SBOM component, because it has no package identity.
- Often no enforced review, because it reads as documentation in a diff.

## The gap this measures

A reviewer approves a pull request. The diff shows a Markdown file. The agent
then follows an instruction that the reviewer read as documentation, or that
arrived from a dependency and was never in any diff at all. The audit trail and
the thing the agent obeyed have come apart.

Ovrin does not judge what a file says. It records what exists, where it
came from, whether review is enforced on it, and which agents would load it, so
a project can see the gap before an agent walks through it.

## Out of scope

- Deciding whether an instruction is malicious. That is content analysis and a person's job.
- Confining an agent at runtime. That is a sandbox.
- Asserting that any agent is vulnerable. The matrix records behaviour, including conservative agents.
