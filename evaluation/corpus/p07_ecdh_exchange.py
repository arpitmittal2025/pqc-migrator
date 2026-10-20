"""Elliptic-curve Diffie-Hellman agreement (key exchange, not signing)."""

from cryptography.hazmat.primitives.asymmetric import ec


def party():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc key_exchange


def agree(private_key, peer_public_key):
    return private_key.exchange(ec.ECDH(), peer_public_key)  # EXPECT: ecc key_exchange
