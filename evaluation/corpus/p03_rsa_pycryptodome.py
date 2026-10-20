"""Key transport using PyCryptodome instead of cryptography."""

from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA


def make_key():
    return RSA.generate(2048)  # EXPECT: rsa kem


def seal(key, data):
    cipher = PKCS1_OAEP.new(key)  # EXPECT: rsa kem
    return cipher.encrypt(data)
