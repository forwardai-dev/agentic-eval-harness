"""Ed25519 signing over canonical bytes — offline, local keys, no network.

Same pattern as AAH's audit/signer.py: a Signer/Verifier pair so evidence is
re-verifiable without trusting the producer's tooling.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


@dataclass
class Ed25519Signer:
    """Ed25519 implementation of the signing protocol."""

    _private: Ed25519PrivateKey

    @classmethod
    def generate(cls, seed: int | None = None) -> "Ed25519Signer":
        """Generate an Ed25519 signer. A fixed seed gives a reproducible demo key."""
        if seed is not None:
            raw = seed.to_bytes(32, "big", signed=False)
            return cls(Ed25519PrivateKey.from_private_bytes(raw))
        return cls(Ed25519PrivateKey.generate())

    def sign(self, data: bytes) -> str:
        """Sign the bytes with the Ed25519 private key; return hex signature."""
        return self._private.sign(data).hex()

    @property
    def public_key_hex(self) -> str:
        """Return the public key as hex."""
        from cryptography.hazmat.primitives import serialization

        raw = self._private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()


class Ed25519Verifier:
    """Ed25519 implementation of the verification protocol."""

    def verify(self, data: bytes, signature_hex: str, public_key_hex: str) -> bool:
        """Return True if the signature is valid for the bytes and public key."""
        try:
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
            pub.verify(bytes.fromhex(signature_hex), data)
            return True
        except (InvalidSignature, ValueError):
            return False


# A fixed demo seed so the signer's public key (and thus the whole evidence
# chain) is reproducible run-to-run without persisting a key file. This is a
# DEMO key only — production use should load a real persistent key (see
# Ed25519Signer + PUBLISHING notes in the AAH repo this pattern was ported from).
DEMO_SEED = 42
