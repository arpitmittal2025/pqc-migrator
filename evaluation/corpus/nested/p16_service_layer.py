"""Crypto in a nested package, to confirm recursive discovery."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def token_key():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc signature


def mint(key, claims):
    return key.sign(claims, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature
