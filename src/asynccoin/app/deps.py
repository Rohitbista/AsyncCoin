import time
import uuid
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, Request, status
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
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise unauthorized

    user = await db.get(User, user_id)
    if user is None or not user.is_active or not user.is_verified:
        raise unauthorized
    return user


class RateLimiter:
    """Small in-memory sliding-window limiter, keyed by client IP + route path.

    Zero extra dependencies. State is per process, so with several workers the
    effective limit is `limit * workers`; swap for Redis/slowapi if you scale out.
    Behind a proxy, set uvicorn's forwarded_allow_ips to the proxy's address so
    request.client.host is the real client and can't be spoofed.
    """

    _MAX_KEYS = 10_000

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[key]

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{ip}"

        if len(self._hits) > self._MAX_KEYS:
            self._prune(now)

        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = max(1, int(self.window - (now - hits[0])))
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests, please try again later",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)


login_limiter = RateLimiter(limit=10, window_seconds=60)
register_limiter = RateLimiter(limit=5, window_seconds=600)
resend_limiter = RateLimiter(limit=5, window_seconds=600)
verify_limiter = RateLimiter(limit=20, window_seconds=600)