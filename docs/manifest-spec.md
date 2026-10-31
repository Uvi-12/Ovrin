# Manifest schema 0.2.0

A JSON document describing every agent instruction file, and every piece of
executing agent configuration, found under a scan root. 0.2.0 adds `execRules`,
`executing`, and `summary.executing`; every 0.1.0 field is unchanged.

## Top level

| Field | Type | Notes |
| --- | --- | --- |
| `schemaVersion` | string | Semver of this schema |
| `generatedAt` | string | RFC 3339 UTC, omitted with `--no-timestamp` |
| `tool` | object | `{name, version}` |
| `harnessRules` | object | Version and verification date of the loading matrix used |
| `subject` | object | Scan root, git status, CODEOWNERS location |
| `execRules` | object | Version and date of the executing-config rules, and agents whose executing config is not repository-local |
| `instructions` | array | One entry per instruction file, sorted by path |
| `executing` | array | One entry per executing configuration file, sorted by path |
| `summary` | object | Counts by origin, family, and risk category; `summary.executing` covers the `executing` array |

## An instruction entry

```json
{
  "path": "node_modules/left-pad/AGENTS.md",
  "family": "agents",
  "activation": "native-auto",
  "digest": null,
  "digestStatus": "oversize",
  "bytes": 3145728,
  "origin": {
    "class": "installed-dependency",
    "container": "node_modules",
    "package": "left-pad@1.3.0",
    "evidence": ["under vendor directory 'node_modules'", "not tracked (installed)"]
  },
  "review": {
    "codeowners": ["@org/platform"],
    "ruleMatches": true,
    "enforceable": false,
    "reason": "path is git-ignored; it never appears in a pull request diff",
    "source": ".github/CODEOWNERS"
  },
  "introducedInAuthorsFirstCommit": null,
  "git": { "tracked": false },
  "gitIgnored": true,
  "reachability": {
    "codex-cli": {
      "verdict": "unverified",
      "reason": "path is git-ignored; harness ignore behaviour not verified",
      "confidence": "documented"
    }
  }
}
```

## An executing entry

```json
{
  "path": ".claude/settings.json",
  "kind": "claude-settings",
  "autoExec": true,
  "launchDir": "",
  "digest": "sha256:...",
  "origin": { "class": "repo", "evidence": ["tracked in git"] },
  "review": { "ruleMatches": true, "enforceable": null, "reason": "..." },
  "gitIgnored": false,
  "loadedBy": {
    "claude-code": {
      "verdict": "loaded",
      "confidence": "observed",
      "reason": "at the repository root, where the agent is launched",
      "source": "research/activation, root placement"
    }
  },
  "parsed": true,
  "parseError": null,
  "capabilities": [
    { "kind": "process_exec",
      "detail": "hook on SessionStart (matcher '*') runs: bash vendor/telemetry-kit/setup.sh" }
  ],
  "runsThirdPartyCode": [
    { "path": "vendor/telemetry-kit/setup.sh", "origin": "vendored",
      "container": "vendor", "package": null }
  ],
  "risk": {
    "blocked": true,
    "reasons": [
      { "severity": "block", "code": "third-party-code",
        "detail": "runs vendored code at vendor/telemetry-kit/setup.sh, outside the project's own reviewed source" }
    ]
  }
}
```

`launchDir` is the directory an agent would have to be launched in to load the
file; `""` means the repository root. A file with a non-empty `launchDir` is
`not-discovered` for every agent and is never reported as loaded.

Capability kinds: `process_exec`, `network_egress`, `credential_ref`, `env_read`,
`permission_grant`, `floating_version`, `bundled_script`. They are facts read
from the file as data. The scanner never runs the file.

Risk codes. `block` reasons fail `--fail-on-exec-risk`; `warn` reasons never do.

| Code | Severity | When |
| --- | --- | --- |
| `unreviewed-exec` | block | Loaded at the root, can run code, and `review.enforceable` is `false` |
| `third-party-code` | block | Loaded at the root and a command runs a path inside a vendored, installed, or submodule location |
| `third-party-config` | block | The file itself is third-party and loads at the root |
| `nested-third-party` | warn | Third-party executing config that loads only from its own directory |
| `model-invoked-exec` | warn | A skill that bundles code and is not covered by enforced review |
| `floating-version` | warn | Loaded at the root and runs a package version that can change without a commit |
| `unparsed` | warn | The file could not be parsed |

## Origin classes

| Class | Meaning |
| --- | --- |
| `repo` | Tracked, in the project's own source tree |
| `workspace` | A declared monorepo workspace member |
| `submodule` | Inside a path registered in `.gitmodules` |
| `vendored` | Inside a committed third-party directory |
| `installed-dependency` | Under a vendor directory but not tracked, so installed rather than committed |
| `untracked` | On disk, not in `git ls-files` |
| `unknown` | Not a git repository |

## Review fields

`ruleMatches` and `enforceable` are separate on purpose. A catch-all `*` rule matches every path, including git-ignored and untracked ones that no pull request touches. So a rule matching a path is not evidence that anyone reviews it.

`enforceable` is `false` for ignored or untracked paths, and `null` for a tracked path that a rule matches, because whether review is actually required depends on branch protection, which is not visible from the filesystem. It is never blindly `true`.

## Reachability verdicts

| Verdict | Meaning |
| --- | --- |
| `loaded` | Within this agent's discovery scope |
| `ignored` | Excluded by ignore rules the agent respects |
| `not-discovered` | Agent does not read this filename or does not walk here |
| `unverified` | Behaviour not established. Not a claim in either direction. |

`unverified` is load-bearing. A tool that guessed here would print a confident table that is wrong for at least one agent, and the whole manifest would deserve to be ignored.

## The digest rule

`digest` is a SHA-256 over the complete file, or `null`. It is never a hash of part of a file. When a file is larger than the hash limit, `digest` is `null` and `digestStatus` says `oversize`. A partial hash under the same field name as a full one would make every downstream comparison silently wrong.

## Stability

Pre-1.0. Fields may be added freely. Removals and renames get a minor bump and a `CHANGELOG` entry.
