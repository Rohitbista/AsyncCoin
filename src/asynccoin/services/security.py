import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from asynccoin.config.settings import settings

_ph = PasswordHasher()

# Verified against when the email doesn't exist, so login takes the same time
# whether or not the account exists (prevents user enumeration via timing).
DUMMY_HASH = _ph.hash("not-a-real-password")


def _hash_password(password: str) -> str:
    return _ph.hash(password)


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Argon2 is deliberately CPU-heavy; run it off the event loop.
async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hash_password, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(_verify_password, password, password_hash)


def generate_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex). Email the raw one, store only the hash."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_access_token(user_id: str) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), expires_in


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError if invalid/expired."""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )