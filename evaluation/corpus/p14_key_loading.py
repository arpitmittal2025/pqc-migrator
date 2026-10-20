"""Loading an existing private key from disk."""

from cryptography.hazmat.primitives import serialization


def load(path):
    with open(path, "rb") as handle:
        return serialization.load_pem_private_key(handle.read(), password=None)  # EXPECT: rsa kem
