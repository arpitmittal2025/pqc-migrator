"""A module whose comments and strings discuss crypto without using it."""

MIGRATION_NOTE = "Replace rsa.generate_private_key with an ML-KEM keypair."

HELP_TEXT = """
Legacy services used ec.generate_private_key and dh.generate_parameters.
Those are documented here for reference only.
"""


def describe():
    # The old handshake relied on dh.generate_parameters for its group.
    return MIGRATION_NOTE
