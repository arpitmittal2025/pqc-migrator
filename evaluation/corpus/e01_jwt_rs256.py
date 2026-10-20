"""RSA signing selected by a string parameter, not by an API call."""

import jwt


def issue(claims, private_key):
    return jwt.encode(claims, private_key, algorithm="RS256")  # EXPECT: rsa signature extended


def check(token, public_key):
    return jwt.decode(token, public_key, algorithms=["RS256"])  # EXPECT: rsa signature extended
