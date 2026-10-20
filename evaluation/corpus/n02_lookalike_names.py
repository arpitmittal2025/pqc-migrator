"""Identifiers that resemble crypto but are ordinary application code."""

RSA_TEAM_CONTACT = "security@example.com"
dh_parameters_table = {"region": "ap-south-1"}


class ECDSALogFormatter:
    """Formats audit entries; nothing cryptographic here."""

    def generate_private_key_id(self, tenant):
        return f"{tenant}-private-key-id"


def padding_for(width, text):
    return text.ljust(width)
