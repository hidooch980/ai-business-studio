import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return _password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _password_hasher.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def issue_session_token() -> tuple[str, str]:
    """Return a high-entropy bearer token and its SHA-256 digest for storage."""
    token = secrets.token_urlsafe(48)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return token, digest


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
