"""SSH host keys through paramiko."""

import paramiko


def rotate_host_key(path):
    key = paramiko.RSAKey.generate(2048)  # EXPECT: rsa signature extended
    key.write_private_key_file(path)
    return key
