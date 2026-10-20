"""Session-key transport with RSA-OAEP (cryptography)."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def build_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem
    return key, key.public_key()


def wrap(public_key, session_key):
    return public_key.encrypt(
        session_key,
        padding.OAEP(  # EXPECT: rsa kem
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def fresh_key():
    return os.urandom(32)
