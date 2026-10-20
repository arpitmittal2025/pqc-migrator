"""Certificate key generation through pyOpenSSL."""

from OpenSSL import crypto


def new_cert_key():
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)  # EXPECT: rsa signature extended
    return key
