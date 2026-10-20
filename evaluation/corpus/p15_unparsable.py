"""Deliberately malformed file: exercises the regex fallback path."""

from cryptography.hazmat.primitives.asymmetric import rsa

def broken(
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem
