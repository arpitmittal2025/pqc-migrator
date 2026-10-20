"""Artifact signing with ECDSA over P-256."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def build_key():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc signature


def sign(key, payload):
    return key.sign(payload, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature


def check(public_key, payload, signature):
    public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature
    return True
