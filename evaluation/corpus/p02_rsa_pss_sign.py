"""Document signing with RSA-PSS."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)  # EXPECT: rsa signature


def sign(key, payload):
    return key.sign(
        payload,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),  # EXPECT: rsa signature
        hashes.SHA256(),
    )
