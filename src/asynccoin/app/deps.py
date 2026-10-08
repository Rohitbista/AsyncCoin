import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.database.models import User
from asynccoin.database.session import get_db
from asynccoin.services.security import decode_access_token

# Adds the "Authorize" button to /docs with a single box where you paste the
# access_token returned by POST /api/auth/login.
# auto_error=False so we return a consistent 401 (not 403) when it's missing.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated or token expired",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized

    user = await db.get(User, user_id)
    if user is None or not user.is_active or not user.is_verified:
        raise unauthorized
    return user