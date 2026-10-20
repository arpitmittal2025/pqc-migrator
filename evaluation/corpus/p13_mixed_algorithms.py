"""One module using RSA for transport and ECDSA for signing."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa


def transport_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem


def wrap(public_key, secret):
    return public_key.encrypt(secret, padding.OAEP(  # EXPECT: rsa kem
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    ))


def identity_key():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc signature


def attest(key, claim):
    return key.sign(claim, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature
