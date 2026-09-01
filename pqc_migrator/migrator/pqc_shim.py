"""Drop-in PQC replacements for the ``cryptography`` asymmetric APIs.

Migrated code imports this module instead of ``cryptography.hazmat.primitives``.
The object model deliberately mirrors the classical one (``generate_private_key``,
``public_key()``, ``encrypt``/``decrypt``, ``sign``/``verify``) so rule-based
rewrites stay small, but every operation underneath is NIST PQC:

* key transport  -> ML-KEM (FIPS 203) encapsulation + AES-256-GCM of the payload
* signatures     -> ML-DSA (FIPS 204), or SLH-DSA (FIPS 205) on the liboqs backend

This file is copied verbatim next to migrated sources by the migrator.
"""

from __future__ import annotations

import os
import struct

from pqc_migrator.pqc import backends

DEFAULT_KEM = "ML-KEM-768"
DEFAULT_SIG = "ML-DSA-65"


class InvalidSignature(Exception):
    """Raised by :meth:`SignaturePublicKey.verify`, mirroring ``cryptography``."""


# --------------------------------------------------------------------------
# Placeholder namespaces: classical padding / hash / encoding options are
# meaningless for PQC but are kept so call sites do not have to change.
# --------------------------------------------------------------------------

class _Ignored:
    """Accepts any construction arguments and carries no behaviour."""

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} ignored by PQC shim>"


class _Namespace:
    """Attribute bag used to emulate the classical module namespaces."""

    def __init__(self, **members) -> None:
        self.__dict__.update(members)


def _ignored_factory(name: str):
    return type(name, (_Ignored,), {})


# hashes.SHA256() etc. -- retained because hash choice still matters for KDFs.
hashes = _Namespace(
    SHA256=_ignored_factory("SHA256"),
    SHA384=_ignored_factory("SHA384"),
    SHA512=_ignored_factory("SHA512"),
)

# padding.OAEP / MGF1 / PSS / PKCS1v15 -- not used by ML-KEM or ML-DSA.
padding = _Namespace(
    OAEP=_ignored_factory("OAEP"),
    MGF1=_ignored_factory("MGF1"),
    PSS=_ignored_factory("PSS"),
    PKCS1v15=_ignored_factory("PKCS1v15"),
)


# --------------------------------------------------------------------------
# Key-encapsulation keys (RSA key transport / Diffie-Hellman replacement)
# --------------------------------------------------------------------------

def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, None)


def _aes_gcm_decrypt(key: bytes, blob: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce, body = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, body, None)


class KEMPublicKey:
    """Encapsulation key; ``encrypt`` performs a KEM/DEM key-transport step."""

    def __init__(self, algorithm: str, key_bytes: bytes) -> None:
        self.algorithm = algorithm
        self.key_bytes = key_bytes

    def encrypt(self, plaintext: bytes, padding=None) -> bytes:
        """ML-KEM encapsulate, then AES-256-GCM the payload under the secret.

        The classical ``padding`` argument is accepted and ignored.
        """
        ciphertext, shared_secret = backends.kem_encapsulate(
            self.algorithm, self.key_bytes
        )
        envelope = _aes_gcm_encrypt(shared_secret, plaintext)
        return struct.pack(">I", len(ciphertext)) + ciphertext + envelope

    def encapsulate(self) -> tuple[bytes, bytes]:
        """Raw KEM interface: returns ``(ciphertext, shared_secret)``."""
        return backends.kem_encapsulate(self.algorithm, self.key_bytes)

    def public_bytes(self, encoding=None, format=None) -> bytes:
        return self.key_bytes

    def __len__(self) -> int:
        return len(self.key_bytes)


class KEMPrivateKey:
    """Decapsulation key, shaped like a classical private key object."""

    def __init__(self, algorithm: str, public_key: bytes, secret_key: bytes) -> None:
        self.algorithm = algorithm
        self._public = KEMPublicKey(algorithm, public_key)
        self.secret_key = secret_key

    def public_key(self) -> KEMPublicKey:
        return self._public

    def decrypt(self, blob: bytes, padding=None) -> bytes:
        """Undo :meth:`KEMPublicKey.encrypt`."""
        (ct_len,) = struct.unpack(">I", blob[:4])
        ciphertext = blob[4 : 4 + ct_len]
        envelope = blob[4 + ct_len :]
        shared_secret = backends.kem_decapsulate(
            self.algorithm, self.secret_key, ciphertext
        )
        return _aes_gcm_decrypt(shared_secret, envelope)

    def decapsulate(self, ciphertext: bytes) -> bytes:
        """Raw KEM interface: returns the shared secret."""
        return backends.kem_decapsulate(self.algorithm, self.secret_key, ciphertext)

    def private_bytes(self, encoding=None, format=None, encryption_algorithm=None) -> bytes:
        """Serialise as ``alg|public|secret``; encoding options are ignored."""
        header = f"{self.algorithm}\n".encode()
        return (
            header
            + struct.pack(">I", len(self._public.key_bytes))
            + self._public.key_bytes
            + self.secret_key
        )

    def exchange(self, peer_public_key) -> bytes:
        """Diffie-Hellman's symmetric agreement has no direct KEM equivalent."""
        raise NotImplementedError(
            "ML-KEM is not a drop-in for DH.exchange(): the handshake must become "
            "an explicit initiator-encapsulates / responder-decapsulates flow. "
            "Use KEMPublicKey.encapsulate() and KEMPrivateKey.decapsulate(), or "
            "the kem_handshake() helper in this module."
            "  # TODO(project-II): LLM-assisted rewrite of the handshake protocol"
        )


def load_private_key(data: bytes, password=None) -> KEMPrivateKey:
    """Inverse of :meth:`KEMPrivateKey.private_bytes`."""
    header, rest = data.split(b"\n", 1)
    algorithm = header.decode()
    (pk_len,) = struct.unpack(">I", rest[:4])
    public_key = rest[4 : 4 + pk_len]
    secret_key = rest[4 + pk_len :]
    return KEMPrivateKey(algorithm, public_key, secret_key)


def kem_handshake(responder_public: KEMPublicKey) -> tuple[bytes, bytes]:
    """Correct replacement for a DH round: initiator side.

    Returns ``(ciphertext_to_send, shared_secret)``; the responder recovers the
    same secret with ``private_key.decapsulate(ciphertext)``.
    """
    return responder_public.encapsulate()


def _generate_kem_key(algorithm: str = DEFAULT_KEM) -> KEMPrivateKey:
    public_key, secret_key = backends.kem_keypair(algorithm)
    return KEMPrivateKey(algorithm, public_key, secret_key)


class KEMParameters:
    """Stands in for ``dh`` parameters; PQC KEMs need no shared parameters."""

    def __init__(self, algorithm: str = DEFAULT_KEM) -> None:
        self.algorithm = algorithm

    def generate_private_key(self) -> KEMPrivateKey:
        return _generate_kem_key(self.algorithm)


# --------------------------------------------------------------------------
# Signature keys (RSA-PSS / ECDSA replacement)
# --------------------------------------------------------------------------

class SignaturePublicKey:
    def __init__(self, algorithm: str, key_bytes: bytes) -> None:
        self.algorithm = algorithm
        self.key_bytes = key_bytes

    def verify(self, signature: bytes, data: bytes, algorithm=None) -> None:
        """Raises :class:`InvalidSignature` on failure, like ``cryptography``."""
        if not backends.sig_verify(self.algorithm, self.key_bytes, data, signature):
            raise InvalidSignature(f"{self.algorithm} signature verification failed")

    def public_bytes(self, encoding=None, format=None) -> bytes:
        return self.key_bytes

    def __len__(self) -> int:
        return len(self.key_bytes)


class SignaturePrivateKey:
    def __init__(self, algorithm: str, public_key: bytes, secret_key: bytes) -> None:
        self.algorithm = algorithm
        self._public = SignaturePublicKey(algorithm, public_key)
        self.secret_key = secret_key

    def public_key(self) -> SignaturePublicKey:
        return self._public

    def sign(self, data: bytes, algorithm=None, padding=None) -> bytes:
        """Sign ``data``; classical padding/hash arguments are ignored."""
        return backends.sig_sign(self.algorithm, self.secret_key, data)

    def private_bytes(self, encoding=None, format=None, encryption_algorithm=None) -> bytes:
        header = f"{self.algorithm}\n".encode()
        return (
            header
            + struct.pack(">I", len(self._public.key_bytes))
            + self._public.key_bytes
            + self.secret_key
        )


def _generate_sig_key(algorithm: str = DEFAULT_SIG) -> SignaturePrivateKey:
    public_key, secret_key = backends.sig_keypair(algorithm)
    return SignaturePrivateKey(algorithm, public_key, secret_key)


def load_signature_private_key(data: bytes, password=None) -> SignaturePrivateKey:
    header, rest = data.split(b"\n", 1)
    algorithm = header.decode()
    (pk_len,) = struct.unpack(">I", rest[:4])
    return SignaturePrivateKey(algorithm, rest[4 : 4 + pk_len], rest[4 + pk_len :])


# --------------------------------------------------------------------------
# Module-shaped namespaces the rewrite rules import
# --------------------------------------------------------------------------

# ``from pqc_shim import rsa`` -> RSA key transport becomes ML-KEM.
rsa = _Namespace(
    generate_private_key=lambda public_exponent=None, key_size=None, algorithm=DEFAULT_KEM, **_: (
        _generate_kem_key(algorithm)
    ),
)

# ``from pqc_shim import ec`` -> ECDSA becomes ML-DSA.
ec = _Namespace(
    generate_private_key=lambda curve=None, algorithm=DEFAULT_SIG, **_: (
        _generate_sig_key(algorithm)
    ),
    ECDSA=_ignored_factory("ECDSA"),
    ECDH=_ignored_factory("ECDH"),
    SECP256R1=_ignored_factory("SECP256R1"),
    SECP384R1=_ignored_factory("SECP384R1"),
    SECP521R1=_ignored_factory("SECP521R1"),
)

# ``from pqc_shim import dh`` -> DH parameters become an ML-KEM keypair factory.
dh = _Namespace(
    generate_parameters=lambda generator=None, key_size=None, algorithm=DEFAULT_KEM, **_: (
        KEMParameters(algorithm)
    ),
)

# ``from pqc_shim import serialization`` -> encoding options kept as no-ops.
serialization = _Namespace(
    Encoding=_Namespace(PEM="PEM", DER="DER", Raw="Raw"),
    PrivateFormat=_Namespace(PKCS8="PKCS8", Raw="Raw", TraditionalOpenSSL="PKCS1"),
    PublicFormat=_Namespace(SubjectPublicKeyInfo="SPKI", Raw="Raw"),
    NoEncryption=_ignored_factory("NoEncryption"),
    BestAvailableEncryption=_ignored_factory("BestAvailableEncryption"),
    load_pem_private_key=load_private_key,
    load_der_private_key=load_private_key,
)
