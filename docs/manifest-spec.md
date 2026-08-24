# Manifest schema 0.1.0

A JSON document describing every agent instruction file found under a scan root.

## Top level

| Field | Type | Notes |
| --- | --- | --- |
| `schemaVersion` | string | Semver of this schema |
| `generatedAt` | string | RFC 3339 UTC, omitted with `--no-timestamp` |
| `tool` | object | `{name, version}` |
| `harnessRules` | object | Version and verification date of the loading matrix used |
| `subject` | object | Scan root, git status, CODEOWNERS location |
| `instructions` | array | One entry per file, sorted by path |
| `summary` | object | Counts by origin, family, and risk category |

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
