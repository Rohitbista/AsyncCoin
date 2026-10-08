import logging
from urllib.parse import urlencode

import httpx

from asynccoin.config.settings import settings

logger = logging.getLogger(__name__)

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


async def _send(client: httpx.AsyncClient, to_email: str, subject: str, html: str) -> None:
    response = await client.post(
        BREVO_SEND_URL,
        headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
        json={
            "sender": {"email": settings.brevo_sender_email, "name": settings.brevo_sender_name},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html,
        },
    )
    response.raise_for_status()


async def send_verification_email(client: httpx.AsyncClient, to_email: str, raw_token: str) -> None:
    """Runs as a background task: never raises (user can hit 'resend')."""
    link = f"{settings.frontend_verify_url}?{urlencode({'token': raw_token})}"

    if not settings.brevo_api_key:
        logger.warning("Brevo not configured. Verification link for %s: %s", to_email, link)
        return

    html = (
        f"<p>Welcome to {settings.brevo_sender_name}!</p>"
        f'<p><a href="{link}">Verify your email</a></p>'
        f"<p>This link expires in {settings.verification_token_ttl_hours} hours. "
        "If you didn't sign up, you can ignore this email.</p>"
    )
    try:
        await _send(client, to_email, "Verify your email", html)
    except httpx.HTTPError as e:
        logger.exception("Brevo send failed for %s: %r", to_email, e)