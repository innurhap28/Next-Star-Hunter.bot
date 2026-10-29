import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app import security
from app.schemas import Credentials
from app.security import (
    PBKDF2_PREFIX,
    SCRYPT_PREFIX,
    hash_password,
    scrypt_available,
    verify_password,
)

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
LEGACY_PASSWORD = "legacy-password-123"
# Fixed-salt hashes in the stored format, so existing DB rows keep verifying.
SCRYPT_HASH = (
    "scrypt$16384$8$1$000102030405060708090a0b0c0d0e0f$"
    "ac8cec622fd40454d0f9d25ce2270712d054380636078bb4116c2ca9c1531d6e"
    "ad64fc8d1f56abe59cad6378b75a3efdbda4bba1b9e4fafc2bce96b0513f7a8a"
)
PBKDF2_HASH = (
    "pbkdf2_sha256$600000$000102030405060708090a0b0c0d0e0f$"
    "02ee91ffec89c8ccfb85a9af7b92c319142a7dad8b39a05e92f5f14f53c82ee8"
)
needs_scrypt = pytest.mark.skipif(not scrypt_available(), reason="hashlib.scrypt unavailable")

@pytest.fixture
def no_scrypt(monkeypatch):
    """Simulate Python builds without hashlib.scrypt (e.g. macOS Python 3.9 + LibreSSL)."""
    monkeypatch.delattr(hashlib, "scrypt", raising=False)
    assert not scrypt_available()
    return monkeypatch

def test_password_hash_is_salted_and_verifiable():
    first, second = hash_password("테스트 password 123"), hash_password("테스트 password 123")
    assert first != second
    assert "password" not in first
    assert verify_password("테스트 password 123", first)
    assert not verify_password("wrong", first)

@needs_scrypt
def test_scrypt_is_used_when_available():
    assert hash_password("password").startswith(SCRYPT_PREFIX + "$")

def test_pbkdf2_fallback_without_scrypt(no_scrypt):
    first, second = hash_password("테스트 password 123"), hash_password("테스트 password 123")
    assert first.startswith(PBKDF2_PREFIX + "$")
    assert int(first.split("$")[1]) >= 600_000
    assert first != second
    assert verify_password("테스트 password 123", first)
    assert not verify_password("wrong", first)

@needs_scrypt
def test_existing_scrypt_hash_still_verifies():
    assert verify_password(LEGACY_PASSWORD, SCRYPT_HASH)
    assert not verify_password("wrong-password", SCRYPT_HASH)

def test_pbkdf2_hash_verifies_with_or_without_scrypt(monkeypatch):
    assert verify_password(LEGACY_PASSWORD, PBKDF2_HASH)
    assert not verify_password("wrong-password", PBKDF2_HASH)
    monkeypatch.delattr(hashlib, "scrypt", raising=False)
    assert verify_password(LEGACY_PASSWORD, PBKDF2_HASH)

@needs_scrypt
def test_hash_made_without_scrypt_verifies_after_scrypt_returns(no_scrypt):
    encoded = hash_password("moved-from-mac-123")
    no_scrypt.undo()
    assert scrypt_available()
    assert verify_password("moved-from-mac-123", encoded)

def test_scrypt_hash_fails_closed_without_scrypt(no_scrypt):
    assert not verify_password(LEGACY_PASSWORD, SCRYPT_HASH)

def test_verification_uses_constant_time_compare(monkeypatch):
    calls = []
    def compare(a, b):
        calls.append((a, b))
        return a == b
    monkeypatch.setattr(security.hmac, "compare_digest", compare)
    assert verify_password(LEGACY_PASSWORD, PBKDF2_HASH)
    assert len(calls) == 1

def _replace(encoded, index, value):
    parts = encoded.split("$")
    parts[index] = value
    return "$".join(parts)

@pytest.mark.parametrize("encoded", [
    "", "plain-password", "scrypt$999999999$8$1$aa$bb", None, 12345, b"scrypt$16384$8$1$aa$bb",
    "pbkdf2_sha256$600000$aa$bb",
    _replace(PBKDF2_HASH, 1, "1"),
    _replace(PBKDF2_HASH, 1, "-600000"),
    _replace(PBKDF2_HASH, 0, "pbkdf2_sha1"),
    _replace(PBKDF2_HASH, 2, "zz" * 16),
    _replace(PBKDF2_HASH, 2, "00" * 8),
    _replace(PBKDF2_HASH, 3, PBKDF2_HASH.split("$")[3][:-2]),
    _replace(PBKDF2_HASH, 3, PBKDF2_HASH.split("$")[3] * 2),
    _replace(SCRYPT_HASH, 1, "1024"),
    _replace(SCRYPT_HASH, 5, SCRYPT_HASH.split("$")[5][:64]),
    "md5$" + PBKDF2_HASH.split("$", 2)[2],
    "extra$" + PBKDF2_HASH,
    PBKDF2_HASH + "$",
])
def test_bad_stored_hashes_fail_closed(encoded):
    assert not verify_password(LEGACY_PASSWORD, encoded)

@pytest.mark.parametrize("encoded", [SCRYPT_HASH, PBKDF2_HASH])
def test_non_string_password_fails_closed(encoded):
    assert not verify_password(None, encoded)

def test_auth_router_imports_without_scrypt():
    # The router builds DUMMY_HASH at import time, which crashed without hashlib.scrypt.
    code = (
        "import hashlib\n"
        "vars(hashlib).pop('scrypt', None)\n"
        "from app.routers import auth\n"
        "from app.security import PBKDF2_PREFIX, verify_password\n"
        "assert auth.DUMMY_HASH.startswith(PBKDF2_PREFIX + '$')\n"
        "assert verify_password('not-a-login-password', auth.DUMMY_HASH)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stderr

@pytest.mark.parametrize("password", ["short", "        ", "a" * 129])
def test_invalid_password_is_rejected(password):
    with pytest.raises(ValidationError):
        Credentials(email="test@example.com", password=password)

def test_credentials_normalize_email_without_trimming_password():
    c = Credentials(email="User@EXAMPLE.COM", password=" password with spaces ")
    assert c.email == "user@example.com"
    assert c.password == " password with spaces "
