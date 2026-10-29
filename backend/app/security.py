"""Salted password hashes; signed cookies contain no password.

scrypt is the default. Some Python builds (e.g. macOS system Python 3.9 with
LibreSSL) have no hashlib.scrypt, so PBKDF2-HMAC-SHA256 is used there instead.
The stored string names the algorithm and its parameters, so either format
is verified with the matching function.
"""
import hashlib
import hmac
import secrets

SALT_BYTES = 16
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_PREFIX = f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}"
PBKDF2_ITERATIONS = 600_000
PBKDF2_DKLEN = 32
PBKDF2_PREFIX = f"pbkdf2_sha256${PBKDF2_ITERATIONS}"

def scrypt_available() -> bool:
    return hasattr(hashlib, "scrypt")

def _scrypt(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                          dklen=SCRYPT_DKLEN)

def _pbkdf2(password: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password, salt, PBKDF2_ITERATIONS, dklen=PBKDF2_DKLEN)

def hash_password(password: str) -> str:
    raw, salt = password.encode("utf-8"), secrets.token_bytes(SALT_BYTES)
    if scrypt_available():
        prefix, digest = SCRYPT_PREFIX, _scrypt(raw, salt)
    else:
        prefix, digest = PBKDF2_PREFIX, _pbkdf2(raw, salt)
    return prefix + "$" + salt.hex() + "$" + digest.hex()

def verify_password(password: str, encoded: str) -> bool:
    """Fail closed: unknown formats or a scrypt hash without scrypt support return False."""
    try:
        prefix, salt_hex, digest_hex = encoded.rsplit("$", 2)
        salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
        if len(salt) != SALT_BYTES:
            return False
        if prefix == SCRYPT_PREFIX and len(digest) == SCRYPT_DKLEN:
            if not scrypt_available():
                return False
            calculated = _scrypt(password.encode("utf-8"), salt)
        elif prefix == PBKDF2_PREFIX and len(digest) == PBKDF2_DKLEN:
            calculated = _pbkdf2(password.encode("utf-8"), salt)
        else:
            return False
        return hmac.compare_digest(calculated, digest)
    except (ValueError, TypeError, AttributeError, UnicodeError):
        return False
