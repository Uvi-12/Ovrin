# Security policy

## Scope

Ovrin is a defensive inventory tool. It reads files and reports on them. It
does not execute instruction files, invoke agents, or send data anywhere.

## Reporting a vulnerability in Ovrin

Open a private security advisory on GitHub, or email the maintainer. We aim to
acknowledge within five working days.

## Reporting a flaw in a coding agent

If your use of Ovrin surfaces a discovery, traversal, or ignore-handling
flaw in an agent rather than in Ovrin itself, report it to that vendor
first.

Do not open a public issue here describing an unpatched agent flaw. Open an
issue saying you have a private report in flight, and we will hold a row in the
loading matrix for it and credit you when the fix lands.

## Research conduct

The associated research uses only benign canaries: a marker file, a loopback
request, a fixed string. We do not open pull requests against repositories we do
not own. Third-party behaviour is measured from public metadata.
