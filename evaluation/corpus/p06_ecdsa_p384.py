"""Higher-strength curve, to exercise the level-scoring rules."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


class ReleaseSigner:
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP384R1())  # EXPECT: ecc signature

    def sign(self, data):
        return self.key.sign(data, ec.ECDSA(hashes.SHA384()))  # EXPECT: ecc signature
