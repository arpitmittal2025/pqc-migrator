"""Demo entry point: establish a session key over an RSA-protected channel."""

from keygen import generate_keypair
from secure_channel import new_session_key, unwrap_session_key, wrap_session_key


def main():
    private_key, public_key = generate_keypair()
    session_key = new_session_key()
    ciphertext = wrap_session_key(public_key, session_key)
    recovered = unwrap_session_key(private_key, ciphertext)
    assert recovered == session_key
    print(f"session key established, {len(ciphertext)} byte wrapped blob")


if __name__ == "__main__":
    main()
