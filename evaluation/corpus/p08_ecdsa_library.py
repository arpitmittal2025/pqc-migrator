"""Signing with the standalone `ecdsa` package."""

from ecdsa import NIST256p, SigningKey


def new_key():
    return SigningKey.generate(curve=NIST256p)  # EXPECT: ecc signature


def sign(key, message):
    return key.sign(message)
