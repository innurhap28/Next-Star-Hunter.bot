"""Salted scrypt password hashes; signed cookies contain no password."""
import hashlib
import hmac
import secrets

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=64)
    return "scrypt$16384$8$1$" + salt.hex() + "$" + digest.hex()

def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if (scheme, n, r, p) != ("scrypt", "16384", "8", "1"):
            return False
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if len(salt) != 16 or len(digest) != 64:
            return False
        calculated = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                                     n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=64)
        return hmac.compare_digest(calculated, digest)
    except (ValueError, TypeError, AttributeError, UnicodeError):
        return False
