"""RSA reached through an aliased import -- a known hard case."""

from cryptography.hazmat.primitives.asymmetric import rsa as asym_rsa


def build():
    return asym_rsa.generate_private_key(  # EXPECT: rsa kem
        public_exponent=65537,
        key_size=2048,
    )
