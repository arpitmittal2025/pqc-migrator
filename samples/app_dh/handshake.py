"""Finite-field Diffie-Hellman key agreement for the legacy handshake."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

GENERATOR = 2
KEY_SIZE = 2048


def build_parameters():
    return dh.generate_parameters(generator=GENERATOR, key_size=KEY_SIZE)


def new_peer(parameters):
    private_key = parameters.generate_private_key()
    return private_key, private_key.public_key()


def derive_shared_secret(private_key, peer_public_key) -> bytes:
    shared = private_key.exchange(peer_public_key)
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"handshake"
    ).derive(shared)
