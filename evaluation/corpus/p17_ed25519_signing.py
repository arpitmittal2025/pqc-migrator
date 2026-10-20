"""EdDSA signing. Ed25519 is elliptic-curve, so Shor breaks it too."""

from cryptography.hazmat.primitives.asymmetric import ed25519


def identity():
    return ed25519.Ed25519PrivateKey.generate()  # EXPECT: ecc signature


def endorse(key, statement):
    return key.sign(statement)
