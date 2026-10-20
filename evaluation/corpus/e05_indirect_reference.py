"""The call site is a local alias bound earlier in the module."""

from cryptography.hazmat.primitives.asymmetric import rsa

make_key = rsa.generate_private_key  # EXPECT: rsa kem


def provision():
    return make_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem extended
