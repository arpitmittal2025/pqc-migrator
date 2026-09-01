"""Wrap a symmetric session key for a peer using RSA-OAEP."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

SESSION_KEY_BYTES = 32


def new_session_key():
    return os.urandom(SESSION_KEY_BYTES)


def wrap_session_key(public_key, session_key):
    """Encrypt the session key so only the holder of the private key can read it."""
    return public_key.encrypt(
        session_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def unwrap_session_key(private_key, ciphertext):
    return private_key.decrypt(
        ciphertext,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
