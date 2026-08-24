"""Password hashing (bcrypt, called directly) and JWT issuance/verification for the login gate.

The user chose to keep this gate (see docs/architecture.md's locked-in decisions) even though
the spec never asks for accounts — real credential handling, unlike Phase 1's frontend-only
stub, which accepted any input.

**Calls `bcrypt` directly instead of going through `passlib`'s `CryptContext`.** `passlib`'s
bcrypt backend probes `bcrypt.__about__.__version__` to detect the installed version, which
`bcrypt>=4.1` removed — that probe then falls through to a self-test using an oversized dummy
password and raises `ValueError: password cannot be longer than 72 bytes`, breaking hashing
entirely regardless of the caller's actual password length. This project's own earlier sibling
project (`forex-ai-dashboard`, see docs/architecture.md's "lessons carried over") hit and
worked around the identical issue the same way. bcrypt's own 72-byte input limit is handled
here by truncating (bcrypt ignores bytes beyond 72 anyway; truncating explicitly just avoids
its exception for the rare very-long password rather than silently mis-hashing it).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import SETTINGS

_BCRYPT_MAX_BYTES = 72


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=SETTINGS.jwt_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SETTINGS.jwt_secret, algorithm=SETTINGS.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Returns the token's subject (email) if valid, None if expired/invalid/tampered --
    never raises, so callers can treat any failure mode identically (unauthenticated)."""
    try:
        payload = jwt.decode(token, SETTINGS.jwt_secret, algorithms=[SETTINGS.jwt_algorithm])
    except jwt.PyJWTError:
        return None
    return payload.get("sub")
