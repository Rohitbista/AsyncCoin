from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from asynccoin.app.deps import get_current_user
from asynccoin.app.schemas_auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from asynccoin.config.settings import settings
from asynccoin.database.models import PURPOSE_VERIFY_EMAIL, User, UserToken
from asynccoin.database.session import get_db
from asynccoin.services.email import send_verification_email
from asynccoin.services.security import (
    DUMMY_HASH,
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Same response whether or not the email already exists (no account enumeration).
_GENERIC_MSG = "If this email can be used, a verification link is on its way."


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _issue_verification(
    db: AsyncSession, user: User, request: Request, background: BackgroundTasks
) -> None:
    now = _now()

    # Cooldown: don't spam inboxes (or Brevo quota) if they just got one.
    cutoff = now - timedelta(seconds=settings.verification_resend_cooldown_seconds)
    recent = await db.scalar(
        select(UserToken.id)
        .where(
            UserToken.user_id == user.id,
            UserToken.purpose == PURPOSE_VERIFY_EMAIL,
            UserToken.created_at > cutoff,
        )
        .limit(1)
    )
    if recent:
        return

    # Invalidate older unused links, then issue a fresh one.
    await db.execute(
        update(UserToken)
        .where(
            UserToken.user_id == user.id,
            UserToken.purpose == PURPOSE_VERIFY_EMAIL,
            UserToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw, hashed = generate_token()
    db.add(
        UserToken(
            user_id=user.id,
            purpose=PURPOSE_VERIFY_EMAIL,
            token_hash=hashed,
            expires_at=now + timedelta(hours=settings.verification_token_ttl_hours),
        )
    )
    await db.commit()
    background.add_task(send_verification_email, request.app.state.http_client, user.email, raw)


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def register(
    body: RegisterRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    email = body.email.lower()
    user = await db.scalar(select(User).where(User.email == email))

    if user is None:
        user = User(email=email, password_hash=await hash_password(body.password))
        db.add(user)
        try:
            await db.commit()
        except IntegrityError:  # two simultaneous registrations for the same email
            await db.rollback()
            return MessageResponse(message=_GENERIC_MSG)
    elif user.is_verified:
        return MessageResponse(message=_GENERIC_MSG)

    # New user, or an existing *unverified* one (resend; password is NOT overwritten).
    await _issue_verification(db, user, request, background)
    return MessageResponse(message=_GENERIC_MSG)


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    # POST (not GET) so email link scanners that prefetch URLs can't burn the token.
    now = _now()
    token = await db.scalar(
        select(UserToken)
        .where(
            UserToken.token_hash == hash_token(body.token),
            UserToken.purpose == PURPOSE_VERIFY_EMAIL,
        )
        .with_for_update()
    )
    if token is None or token.used_at is not None or token.expires_at < now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired verification link")

    user = await db.get(User, token.user_id)
    token.used_at = now
    user.is_verified = True
    user.email_verified_at = now
    await db.commit()
    return MessageResponse(message="Email verified. You can now log in.")


@router.post("/resend-verification", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user is not None and not user.is_verified and user.is_active:
        await _issue_verification(db, user, request, background)
    return MessageResponse(message=_GENERIC_MSG)


async def _authenticate(db: AsyncSession, email: str, password: str) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == email.lower()))

    # Always run one hash verification so timing doesn't reveal if the email exists.
    password_ok = await verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please verify your email before logging in")

    user.last_login_at = _now()
    await db.commit()

    token, expires_in = create_access_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Log in with email + password. Copy the returned access_token into Authorize."""
    return await _authenticate(db, body.email, body.password)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user