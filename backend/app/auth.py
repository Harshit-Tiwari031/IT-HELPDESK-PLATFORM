"""Reusable session and role dependencies. Resource routes adopt these in a later phase."""

import hmac
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth_security import hash_session_token
from app.config import Settings, get_settings
from app.database import get_db
from app.models import AuthSession, User


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required.", headers={"WWW-Authenticate": "Cookie"})


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise unauthorized()

    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(token)))
    if session is None or session.revoked_at is not None:
        raise unauthorized()
    now = datetime.now(timezone.utc)
    if _utc(session.expires_at) <= now:
        session.revoked_at = now
        db.commit()
        raise unauthorized()

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        session.revoked_at = now
        db.commit()
        raise unauthorized()
    return user


def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access is required.")
    return user


def require_allowed_origin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    if request.headers.get("origin") not in settings.allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request origin is not allowed.")


def require_csrf(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    require_allowed_origin(request, settings)

    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A valid CSRF token is required.")
