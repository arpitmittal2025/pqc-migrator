"""Diffie-Hellman with an explicitly pinned group."""

from cryptography.hazmat.primitives.asymmetric import dh

P = 23
G = 5


def load_group():
    numbers = dh.DHParameterNumbers(P, G)  # EXPECT: dh key_exchange
    return numbers.parameters()
