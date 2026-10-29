import pytest
from pydantic import ValidationError
from app.security import hash_password, verify_password
from app.schemas import Credentials

def test_password_hash_is_salted_and_verifiable():
    first, second = hash_password("테스트 password 123"), hash_password("테스트 password 123")
    assert first != second
    assert "password" not in first
    assert verify_password("테스트 password 123", first)
    assert not verify_password("wrong", first)

@pytest.mark.parametrize("encoded", ["", "plain-password", "scrypt$999999999$8$1$aa$bb", None])
def test_bad_stored_hashes_fail_closed(encoded):
    assert not verify_password("password", encoded)

@pytest.mark.parametrize("password", ["short", "        ", "a" * 129])
def test_invalid_password_is_rejected(password):
    with pytest.raises(ValidationError):
        Credentials(email="test@example.com", password=password)

def test_credentials_normalize_email_without_trimming_password():
    c = Credentials(email="User@EXAMPLE.COM", password=" password with spaces ")
    assert c.email == "user@example.com"
    assert c.password == " password with spaces "
