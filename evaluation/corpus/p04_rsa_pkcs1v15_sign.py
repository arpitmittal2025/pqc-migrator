"""Legacy PKCS#1 v1.5 signing with PyCryptodome."""

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15


def issue_key():
    return RSA.generate(2048)  # EXPECT: rsa signature


def sign_receipt(key, blob):
    digest = SHA256.new(blob)
    return pkcs1_15.new(key).sign(digest)  # EXPECT: rsa signature
