"""Demo entry point: sign and verify a release artifact."""

from signer import generate_signing_key, sign_artifact, verify_artifact


def main():
    private_key = generate_signing_key()
    payload = b"release-1.4.2.tar.gz"
    signature = sign_artifact(private_key, payload)
    ok = verify_artifact(private_key.public_key(), payload, signature)
    print(f"signature valid: {ok}, {len(signature)} bytes")


if __name__ == "__main__":
    main()
