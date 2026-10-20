"""X25519 key agreement, as used by modern TLS and WireGuard."""

from cryptography.hazmat.primitives.asymmetric import x25519


def endpoint():
    return x25519.X25519PrivateKey.generate()  # EXPECT: ecc key_exchange


def agree(private_key, peer_public):
    return private_key.exchange(peer_public)
