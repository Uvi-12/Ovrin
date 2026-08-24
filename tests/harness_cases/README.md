# Harness cases

One directory per verified behaviour. A case is what turns a row in
`docs/loading-matrix.md` from `documented` into `observed`.

```
<agent-id>/<case-name>/
  RESULT.md    agent version, command, outcome, how confirmed
  repo/        the exact layout under test
  canary.txt   what the instruction asked for, and what appeared
```

Canaries are inert: a marker file, a fixed string, a loopback request. Never
credentials, never a real destination, never anything harmful if copied.
