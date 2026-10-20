"""Generate the labelled detection benchmark used in the evaluation.

Ground truth is embedded in the corpus itself: every line that a cryptography
expert would flag carries a trailing ``# EXPECT: <algorithm> <purpose>`` marker.
Comments cannot influence the detector (the AST ignores them and the regex pass
strips them), so the labels stay independent of the thing being measured.

Run:  python evaluation/build_corpus.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"
LABELS_FILE = Path(__file__).parent / "labels.json"

EXPECT_RE = re.compile(
    r"#\s*EXPECT:\s*(?P<alg>\w+)\s+(?P<purpose>\w+)(?:\s+(?P<scope>core|extended))?"
)

# --------------------------------------------------------------------------
# Positive cases: files that genuinely use quantum-vulnerable public-key crypto
# --------------------------------------------------------------------------

FILES: dict[str, str] = {}

FILES["p01_rsa_oaep.py"] = '''\
"""Session-key transport with RSA-OAEP (cryptography)."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def build_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem
    return key, key.public_key()


def wrap(public_key, session_key):
    return public_key.encrypt(
        session_key,
        padding.OAEP(  # EXPECT: rsa kem
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def fresh_key():
    return os.urandom(32)
'''

FILES["p02_rsa_pss_sign.py"] = '''\
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
'''

FILES["p03_rsa_pycryptodome.py"] = '''\
"""Key transport using PyCryptodome instead of cryptography."""

from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA


def make_key():
    return RSA.generate(2048)  # EXPECT: rsa kem


def seal(key, data):
    cipher = PKCS1_OAEP.new(key)  # EXPECT: rsa kem
    return cipher.encrypt(data)
'''

FILES["p04_rsa_pkcs1v15_sign.py"] = '''\
"""Legacy PKCS#1 v1.5 signing with PyCryptodome."""

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15


def issue_key():
    return RSA.generate(2048)  # EXPECT: rsa signature


def sign_receipt(key, blob):
    digest = SHA256.new(blob)
    return pkcs1_15.new(key).sign(digest)  # EXPECT: rsa signature
'''

FILES["p05_ecdsa_p256.py"] = '''\
"""Artifact signing with ECDSA over P-256."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def build_key():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc signature


def sign(key, payload):
    return key.sign(payload, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature


def check(public_key, payload, signature):
    public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature
    return True
'''

FILES["p06_ecdsa_p384.py"] = '''\
"""Higher-strength curve, to exercise the level-scoring rules."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


class ReleaseSigner:
    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP384R1())  # EXPECT: ecc signature

    def sign(self, data):
        return self.key.sign(data, ec.ECDSA(hashes.SHA384()))  # EXPECT: ecc signature
'''

FILES["p07_ecdh_exchange.py"] = '''\
"""Elliptic-curve Diffie-Hellman agreement (key exchange, not signing)."""

from cryptography.hazmat.primitives.asymmetric import ec


def party():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc key_exchange


def agree(private_key, peer_public_key):
    return private_key.exchange(ec.ECDH(), peer_public_key)  # EXPECT: ecc key_exchange
'''

FILES["p08_ecdsa_library.py"] = '''\
"""Signing with the standalone `ecdsa` package."""

from ecdsa import NIST256p, SigningKey


def new_key():
    return SigningKey.generate(curve=NIST256p)  # EXPECT: ecc signature


def sign(key, message):
    return key.sign(message)
'''

FILES["p09_dh_handshake.py"] = '''\
"""Finite-field Diffie-Hellman handshake."""

from cryptography.hazmat.primitives.asymmetric import dh


def parameters():
    return dh.generate_parameters(generator=2, key_size=2048)  # EXPECT: dh key_exchange


def peer(params):
    private_key = params.generate_private_key()
    return private_key, private_key.public_key()


def shared(private_key, peer_public):
    return private_key.exchange(peer_public)
'''

FILES["p10_dh_fixed_group.py"] = '''\
"""Diffie-Hellman with an explicitly pinned group."""

from cryptography.hazmat.primitives.asymmetric import dh

P = 23
G = 5


def load_group():
    numbers = dh.DHParameterNumbers(P, G)  # EXPECT: dh key_exchange
    return numbers.parameters()
'''

FILES["p11_aliased_import.py"] = '''\
"""RSA reached through an aliased import -- a known hard case."""

from cryptography.hazmat.primitives.asymmetric import rsa as asym_rsa


def build():
    return asym_rsa.generate_private_key(  # EXPECT: rsa kem
        public_exponent=65537,
        key_size=2048,
    )
'''

FILES["p12_multiline_call.py"] = '''\
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
'''

FILES["p13_mixed_algorithms.py"] = '''\
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
'''

FILES["p14_key_loading.py"] = '''\
"""Loading an existing private key from disk."""

from cryptography.hazmat.primitives import serialization


def load(path):
    with open(path, "rb") as handle:
        return serialization.load_pem_private_key(handle.read(), password=None)  # EXPECT: rsa kem
'''

FILES["p15_unparsable.py"] = '''\
"""Deliberately malformed file: exercises the regex fallback path."""

from cryptography.hazmat.primitives.asymmetric import rsa

def broken(
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem
'''

FILES["nested/p16_service_layer.py"] = '''\
"""Crypto in a nested package, to confirm recursive discovery."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec


def token_key():
    return ec.generate_private_key(ec.SECP256R1())  # EXPECT: ecc signature


def mint(key, claims):
    return key.sign(claims, ec.ECDSA(hashes.SHA256()))  # EXPECT: ecc signature
'''

FILES["p17_ed25519_signing.py"] = '''"""EdDSA signing. Ed25519 is elliptic-curve, so Shor breaks it too."""

from cryptography.hazmat.primitives.asymmetric import ed25519


def identity():
    return ed25519.Ed25519PrivateKey.generate()  # EXPECT: ecc signature


def endorse(key, statement):
    return key.sign(statement)
'''

FILES["p18_x25519_agreement.py"] = '''"""X25519 key agreement, as used by modern TLS and WireGuard."""

from cryptography.hazmat.primitives.asymmetric import x25519


def endpoint():
    return x25519.X25519PrivateKey.generate()  # EXPECT: ecc key_exchange


def agree(private_key, peer_public):
    return private_key.exchange(peer_public)
'''

# --------------------------------------------------------------------------
# Extended cases: quantum-vulnerable, but reached in ways outside the stated
# scope of this prototype (wrapper libraries, dynamic dispatch, dataflow).
# They are measured separately and reported as coverage limits.
# --------------------------------------------------------------------------

FILES["e01_jwt_rs256.py"] = '''"""RSA signing selected by a string parameter, not by an API call."""

import jwt


def issue(claims, private_key):
    return jwt.encode(claims, private_key, algorithm="RS256")  # EXPECT: rsa signature extended


def check(token, public_key):
    return jwt.decode(token, public_key, algorithms=["RS256"])  # EXPECT: rsa signature extended
'''

FILES["e02_paramiko_hostkey.py"] = '''"""SSH host keys through paramiko."""

import paramiko


def rotate_host_key(path):
    key = paramiko.RSAKey.generate(2048)  # EXPECT: rsa signature extended
    key.write_private_key_file(path)
    return key
'''

FILES["e03_pyopenssl_cert.py"] = '''"""Certificate key generation through pyOpenSSL."""

from OpenSSL import crypto


def new_cert_key():
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)  # EXPECT: rsa signature extended
    return key
'''

FILES["e04_dynamic_dispatch.py"] = '''"""The primitive is chosen at runtime by name."""

from cryptography.hazmat.primitives.asymmetric import rsa

FACTORY = "generate_private_key"


def build(size=2048):
    factory = getattr(rsa, FACTORY)  # EXPECT: rsa kem extended
    return factory(public_exponent=65537, key_size=size)  # EXPECT: rsa kem extended
'''

FILES["e05_indirect_reference.py"] = '''"""The call site is a local alias bound earlier in the module."""

from cryptography.hazmat.primitives.asymmetric import rsa

make_key = rsa.generate_private_key  # EXPECT: rsa kem


def provision():
    return make_key(public_exponent=65537, key_size=2048)  # EXPECT: rsa kem extended
'''

# --------------------------------------------------------------------------
# Negative cases: no quantum-vulnerable public-key cryptography at all
# --------------------------------------------------------------------------

FILES["n01_symmetric_only.py"] = '''\
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
'''

FILES["n02_lookalike_names.py"] = '''\
"""Identifiers that resemble crypto but are ordinary application code."""

RSA_TEAM_CONTACT = "security@example.com"
dh_parameters_table = {"region": "ap-south-1"}


class ECDSALogFormatter:
    """Formats audit entries; nothing cryptographic here."""

    def generate_private_key_id(self, tenant):
        return f"{tenant}-private-key-id"


def padding_for(width, text):
    return text.ljust(width)
'''

FILES["n03_documentation_text.py"] = '''\
"""A module whose comments and strings discuss crypto without using it."""

MIGRATION_NOTE = "Replace rsa.generate_private_key with an ML-KEM keypair."

HELP_TEXT = """
Legacy services used ec.generate_private_key and dh.generate_parameters.
Those are documented here for reference only.
"""


def describe():
    # The old handshake relied on dh.generate_parameters for its group.
    return MIGRATION_NOTE
'''

FILES["n04_already_post_quantum.py"] = '''\
"""Already migrated: uses ML-KEM, so nothing should be reported."""

from kyber_py.ml_kem import ML_KEM_768


def establish():
    encapsulation_key, decapsulation_key = ML_KEM_768.keygen()
    shared_secret, ciphertext = ML_KEM_768.encaps(encapsulation_key)
    return decapsulation_key, ciphertext, shared_secret
'''

FILES["n05_plain_application.py"] = '''\
"""Ordinary business logic with no cryptography of any kind."""

from dataclasses import dataclass


@dataclass
class Invoice:
    number: str
    amount: float

    def with_tax(self, rate):
        return self.amount * (1 + rate)


def total(invoices):
    return sum(invoice.amount for invoice in invoices)
'''

FILES["n06_modern_symmetric.py"] = '''"""ChaCha20-Poly1305 and PBKDF2: quantum-resistant enough, nothing to migrate."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive(password, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
    return kdf.derive(password)


def seal(key, message):
    nonce = os.urandom(12)
    return nonce + ChaCha20Poly1305(key).encrypt(nonce, message, None)
'''

def build() -> dict:
    """Write the corpus to disk and extract ground truth from EXPECT markers."""
    labels: list[dict] = []
    written = 0

    for relative, source in FILES.items():
        path = CORPUS_DIR / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        written += 1

        for number, line in enumerate(source.splitlines(), start=1):
            match = EXPECT_RE.search(line)
            if match:
                labels.append(
                    {
                        "file": relative.replace("\\", "/"),
                        "line": number,
                        "algorithm": match.group("alg"),
                        "purpose": match.group("purpose"),
                        "scope": match.group("scope") or "core",
                    }
                )

    manifest = {
        "files": sorted(FILES),
        "positive_files": sorted(
            f for f in FILES if not Path(f).name.startswith(("n0", "e0"))
        ),
        "extended_files": sorted(f for f in FILES if Path(f).name.startswith("e0")),
        "negative_files": sorted(f for f in FILES if Path(f).name.startswith("n0")),
        "labels": labels,
    }
    LABELS_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    manifest = build()
    core = [l for l in manifest["labels"] if l["scope"] == "core"]
    extended = [l for l in manifest["labels"] if l["scope"] == "extended"]
    print(f"corpus files : {len(manifest['files'])}")
    print(f"  in-scope   : {len(manifest['positive_files'])}")
    print(f"  extended   : {len(manifest['extended_files'])}")
    print(f"  clean      : {len(manifest['negative_files'])}")
    print(f"labelled sites: {len(core)} core + {len(extended)} extended")
