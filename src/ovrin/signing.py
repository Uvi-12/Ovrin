"""Detached Ed25519 signatures for Ovrin manifests.

Provenance is the whole point of Ovrin, so the manifest it produces should
itself be attestable. We sign the canonical bytes of the manifest with an
asymmetric key: a verifier holding only the public key can confirm the manifest
has not changed and was produced by the holder of the private key, but cannot
forge a new one. (A symmetric HMAC cannot offer that: anyone able to verify can
also mint. That distinction is exactly the one the research makes about
approval tokens.)

This module imports ``cryptography`` lazily, so the base install stays
dependency-light; signing/verifying needs ``pip install ".[sign]"``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__

_ALG = "ed25519"


def _need_crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "signing requires the 'cryptography' package; install with "
            "pip install \"ovrin[sign]\""
        ) from exc
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519


def canonical_bytes(manifest: dict[str, Any]) -> bytes:
    """Deterministic byte serialization the signature is computed over.

    Keys are sorted and whitespace is fixed so the same manifest always yields
    the same bytes. Run ``ovrin scan --no-timestamp`` for a signature that is
    stable across runs.
    """
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_digest(manifest: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def generate_keypair(private_path: Path, public_path: Path) -> None:
    ed25519 = _need_crypto()
    from cryptography.hazmat.primitives import serialization

    key = ed25519.Ed25519PrivateKey.generate()
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_path.write_bytes(priv)
    try:
        private_path.chmod(0o600)
    except OSError:  # pragma: no cover - platform dependent
        pass
    public_path.write_text(pub.hex() + "\n", encoding="utf-8")


def sign_manifest(manifest: dict[str, Any], private_key_path: Path) -> dict[str, Any]:
    ed25519 = _need_crypto()
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise RuntimeError("key is not an Ed25519 private key")
    payload = canonical_bytes(manifest)
    sig = key.sign(payload)
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "ovrinSignature": "1",
        "alg": _ALG,
        "created": datetime.now(timezone.utc).isoformat(),
        "ovrinVersion": __version__,
        "digest": manifest_digest(manifest),
        "publicKey": pub.hex(),
        "signature": sig.hex(),
    }


def verify_manifest(
    manifest: dict[str, Any], signature: dict[str, Any], public_key_hex: str | None = None
) -> bool:
    """Return True iff ``signature`` is a valid Ed25519 signature over
    ``manifest``. If ``public_key_hex`` is given, the signature's embedded key
    must match it (pin the signer); otherwise the embedded key is used.
    """
    ed25519 = _need_crypto()
    from cryptography.exceptions import InvalidSignature

    embedded = signature.get("publicKey", "")
    if public_key_hex is not None and embedded.lower() != public_key_hex.lower():
        return False
    if signature.get("digest") and signature["digest"] != manifest_digest(manifest):
        return False
    try:
        pub = ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(embedded))
        pub.verify(bytes.fromhex(signature.get("signature", "")), canonical_bytes(manifest))
        return True
    except (InvalidSignature, ValueError):
        return False
