"""Password/JWT security and dependency-injected identity authorization."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import RefreshSession, User
from app.models.identity import utc_now

JWT_ISSUER = "kinetix-ai"
JWT_AUDIENCE = "kinetix-api"
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
password_hasher = PasswordHasher()
# Unknown accounts still pay the same Argon2 verification cost as known accounts.
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(auto_error=False)
Database = Annotated[Session, Depends(get_db)]


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def password_matches(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def access_token(user: User, session_id: str, session_expires_at: datetime) -> str:
    now = utc_now()
    expires_at = min(now + timedelta(minutes=settings.access_token_minutes), as_utc(session_expires_at))
    return jwt.encode(
        {
            "sub": user.id,
            "sid": session_id,
            "type": "access",
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": now,
            "exp": expires_at,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes, while PostgreSQL preserves their timezone.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
    )


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Database,
) -> User:
    """Return the database User only while their access token and session are valid."""
    if credentials is None:
        raise unauthorized()
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "sid", "type", "iss", "aud", "iat", "exp"]},
        )
        if claims["type"] != "access":
            raise ValueError("Wrong token type")
        user_id, session_id = claims["sub"], claims["sid"]
        if not isinstance(user_id, str) or not isinstance(session_id, str):
            raise ValueError("Invalid identity")
        UUID(user_id)
        UUID(session_id)
    except (jwt.PyJWTError, ValueError, TypeError):
        raise unauthorized() from None
    user = db.scalar(
        select(User)
        .join(RefreshSession, RefreshSession.user_id == User.id)
        .where(
            User.id == user_id,
            RefreshSession.id == session_id,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > utc_now(),
        )
    )
    if user is None:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    """Authorize against the current persisted role, never a client/JWT role claim."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user


def _origin(value: str, *, referer: bool = False) -> str | None:
    try:
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or (not referer and (parts.path not in {"", "/"} or parts.query or parts.fragment))
        ):
            return None
        host = parts.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        if port is not None and (parts.scheme, port) not in {("http", 80), ("https", 443)}:
            host = f"{host}:{port}"
        return f"{parts.scheme}://{host}"
    except ValueError:
        return None


def require_trusted_origin(request: Request) -> None:
    """Reject browser CSRF, including login CSRF, before setting or using cookies."""
    allowed = {_origin(str(request.base_url)), *(_origin(origin) for origin in settings.cors_origins)}
    allowed.discard(None)
    origin = request.headers.get("origin")
    if origin is not None:
        if _origin(origin) in allowed:
            return
    else:
        referer = request.headers.get("referer")
        if referer is not None:
            if _origin(referer, referer=True) in allowed:
                return
        elif request.headers.get("sec-fetch-site") == "same-origin":
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Untrusted request origin")


def set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    expires_at = as_utc(expires_at)
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=max(0, int((expires_at - utc_now()).total_seconds())),
        expires=expires_at,
        httponly=settings.refresh_cookie_httponly,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path=settings.refresh_cookie_path,
    )
    prevent_caching(response)


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        httponly=settings.refresh_cookie_httponly,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
    )
    prevent_caching(response)


def prevent_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
