"""AES-GCM and HMAC: symmetric primitives are not broken by Shor."""

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt(key, plaintext):
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def tag(key, message):
    return hmac.new(key, message, hashlib.sha256).digest()
