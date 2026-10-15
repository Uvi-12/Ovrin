"""Ed25519 detached signatures over the manifest (optional [sign] extra)."""
import pytest

pytest.importorskip("cryptography")

from ovrin.harness import Rules            # noqa: E402
from ovrin.manifest import build           # noqa: E402
from ovrin.signing import (                # noqa: E402
    generate_keypair,
    sign_manifest,
    verify_manifest,
)


def _manifest(repo):
    return build(repo, Rules.load(), no_timestamp=True)


def test_sign_verify_roundtrip(repo, tmp_path):
    m = _manifest(repo)
    priv, pub = tmp_path / "k.key", tmp_path / "k.pub"
    generate_keypair(priv, pub)
    sig = sign_manifest(m, priv)
    assert sig["alg"] == "ed25519"
    assert verify_manifest(m, sig) is True
    assert verify_manifest(m, sig, public_key_hex=pub.read_text().strip()) is True


def test_tamper_detected(repo, tmp_path):
    m = _manifest(repo)
    priv, pub = tmp_path / "k.key", tmp_path / "k.pub"
    generate_keypair(priv, pub)
    sig = sign_manifest(m, priv)
    m["summary"]["total"] = 9999
    assert verify_manifest(m, sig) is False


def test_wrong_key_rejected(repo, tmp_path):
    m = _manifest(repo)
    p1, u1 = tmp_path / "a.key", tmp_path / "a.pub"
    p2, u2 = tmp_path / "b.key", tmp_path / "b.pub"
    generate_keypair(p1, u1)
    generate_keypair(p2, u2)
    sig = sign_manifest(m, p1)
    assert verify_manifest(m, sig, public_key_hex=u2.read_text().strip()) is False
