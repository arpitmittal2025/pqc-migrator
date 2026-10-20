"""Key generation split across several lines inside a class."""

from cryptography.hazmat.primitives.asymmetric import rsa


class KeyService:
    """Issues tenant keys on demand."""

    SIZE = 4096

    def issue(self):
        return rsa.generate_private_key(  # EXPECT: rsa kem
            public_exponent=65537,
            key_size=self.SIZE,
        )
