"""Already migrated: uses ML-KEM, so nothing should be reported."""

from kyber_py.ml_kem import ML_KEM_768


def establish():
    encapsulation_key, decapsulation_key = ML_KEM_768.keygen()
    shared_secret, ciphertext = ML_KEM_768.encaps(encapsulation_key)
    return decapsulation_key, ciphertext, shared_secret
