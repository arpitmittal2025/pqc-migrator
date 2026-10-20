"""Finite-field Diffie-Hellman handshake."""

from cryptography.hazmat.primitives.asymmetric import dh


def parameters():
    return dh.generate_parameters(generator=2, key_size=2048)  # EXPECT: dh key_exchange


def peer(params):
    private_key = params.generate_private_key()
    return private_key, private_key.public_key()


def shared(private_key, peer_public):
    return private_key.exchange(peer_public)
