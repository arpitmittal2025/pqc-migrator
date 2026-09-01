"""Legacy key management for the demo app: RSA-2048 keypairs on disk."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_SIZE = 2048


def generate_keypair():
    """Create a fresh RSA private/public keypair."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
    return private_key, private_key.public_key()


def save_private_key(private_key, path):
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(path, "wb") as handle:
        handle.write(pem)


def load_private_key(path):
    with open(path, "rb") as handle:
        return serialization.load_pem_private_key(handle.read(), password=None)
