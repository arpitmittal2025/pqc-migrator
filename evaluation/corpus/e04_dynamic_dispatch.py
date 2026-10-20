"""The primitive is chosen at runtime by name."""

from cryptography.hazmat.primitives.asymmetric import rsa

FACTORY = "generate_private_key"


def build(size=2048):
    factory = getattr(rsa, FACTORY)  # EXPECT: rsa kem extended
    return factory(public_exponent=65537, key_size=size)  # EXPECT: rsa kem extended
