# Signing manifests

Ovrin's output is a provenance record, so it should itself be attestable. The
`[sign]` extra adds Ed25519 detached signatures over the manifest.

```
pip install ".[sign]"

ovrin keygen --out-dir .ovrin-keys           # ovrin-signing.key (private), .pub (public)
ovrin scan . -f json --no-timestamp -o m.json
ovrin sign m.json --key .ovrin-keys/ovrin-signing.key -o m.json.sig
ovrin verify m.json --sig m.json.sig --pub .ovrin-keys/ovrin-signing.pub
```

The signature covers the manifest's canonical bytes (sorted keys, fixed
whitespace). Run `scan --no-timestamp` for a signature stable across runs.

**Why asymmetric.** A verifier holding the public key can confirm a manifest was
produced by the private-key holder and has not changed, but cannot forge a new
one. A symmetric HMAC cannot offer that separation — anyone able to verify can
also mint. Keep `ovrin-signing.key` out of the repository (it is covered by the
shipped `.gitignore`).
