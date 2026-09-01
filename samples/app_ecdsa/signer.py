"""Release-artifact signing with ECDSA over NIST P-256."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def generate_signing_key():
    return ec.generate_private_key(ec.SECP256R1())


def sign_artifact(private_key, payload: bytes) -> bytes:
    return private_key.sign(payload, ec.ECDSA(hashes.SHA256()))


def verify_artifact(public_key, payload: bytes, signature: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature

    try:
        public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False
