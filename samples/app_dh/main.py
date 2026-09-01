"""Demo entry point: two peers agree on a shared secret."""

from handshake import build_parameters, derive_shared_secret, new_peer


def main():
    parameters = build_parameters()
    alice_priv, alice_pub = new_peer(parameters)
    bob_priv, bob_pub = new_peer(parameters)
    assert derive_shared_secret(alice_priv, bob_pub) == derive_shared_secret(
        bob_priv, alice_pub
    )
    print("shared secret agreed")


if __name__ == "__main__":
    main()
