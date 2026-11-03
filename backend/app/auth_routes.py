"""Email/password identity, rotating refresh cookies, and session revocation."""

import secrets
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
    DUMMY_PASSWORD_HASH,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Database,
    access_token,
    clear_refresh_cookie,
    hash_refresh_token,
    password_hasher,
    password_matches,
    prevent_caching,
    require_trusted_origin,
    set_refresh_cookie,
)
from app.auth_rate_limit import login_rate_limit, refresh_rate_limit, register_rate_limit
from app.config import settings
from app.email_address import canonical_email
from app.models import RefreshSession, RefreshToken, User
from app.models.identity import utc_now

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return canonical_email(value) if isinstance(value, str) else value


class Registration(Credentials):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: Literal["user", "admin"]


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse


def auth_response(user: User, session_id: str, expires_at: datetime) -> AuthResponse:
    return AuthResponse(
        access_token=access_token(user, session_id, expires_at),
        user=UserResponse.model_validate(user),
    )


def create_session(db: Session, user: User) -> tuple[RefreshSession, str]:
    token = secrets.token_urlsafe(48)
    token_hash = hash_refresh_token(token)
    session = RefreshSession(
        user_id=user.id,
        current_token_hash=token_hash,
        expires_at=utc_now() + timedelta(days=settings.refresh_token_days),
    )
    db.add(session)
    db.flush()
    db.add(RefreshToken(token_hash=token_hash, session_id=session.id))
    return session, token


def invalid_refresh() -> JSONResponse:
    response = JSONResponse(
        status_code=401,
        content={"detail": "Refresh session is invalid or expired"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    clear_refresh_cookie(response)
    return response


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    dependencies=[Depends(require_trusted_origin), Depends(register_rate_limit)],
)
def register(credentials: Registration, response: Response, db: Database) -> AuthResponse:
    user = User(
        email=credentials.email,
        password_hash=password_hasher.hash(credentials.password),
        role="admin" if credentials.email == settings.admin_email else "user",
    )
    db.add(user)
    try:
        db.flush()
        session, token = create_session(db, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.scalar(select(User.id).where(User.email == credentials.email)) is not None:
            raise HTTPException(status_code=409, detail="An account with this email already exists") from None
        raise
    set_refresh_cookie(response, token, session.expires_at)
    return auth_response(user, session.id, session.expires_at)


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(require_trusted_origin), Depends(login_rate_limit)],
)
def login(credentials: Credentials, response: Response, db: Database) -> AuthResponse:
    # Serialize with server-side password changes so an old password cannot
    # create a session after that password change has revoked existing ones.
    user = db.scalar(select(User).where(User.email == credentials.email).with_for_update())
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    valid_password = password_matches(stored_hash, credentials.password)
    if user is None or not valid_password:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
            headers={"Cache-Control": "no-store", "WWW-Authenticate": "Bearer"},
        )
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = password_hasher.hash(credentials.password)
    session, token = create_session(db, user)
    db.commit()
    set_refresh_cookie(response, token, session.expires_at)
    return auth_response(user, session.id, session.expires_at)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    dependencies=[Depends(require_trusted_origin), Depends(refresh_rate_limit)],
)
def refresh(request: Request, response: Response, db: Database) -> AuthResponse | Response:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token or len(token) > 256:
        return invalid_refresh()
    token_hash = hash_refresh_token(token)
    previous = db.get(RefreshToken, token_hash)
    if previous is None:
        return invalid_refresh()
    replacement = secrets.token_urlsafe(48)
    replacement_hash = hash_refresh_token(replacement)
    now = utc_now()
    # PostgreSQL/SQLite serialize this compare-and-swap. A losing concurrent
    # refresh sees the retained old hash and revokes the entire session family.
    rotated = db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == previous.session_id,
            RefreshSession.current_token_hash == token_hash,
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > now,
        )
        .values(current_token_hash=replacement_hash)
        .returning(RefreshSession.id, RefreshSession.user_id, RefreshSession.expires_at),
        execution_options={"synchronize_session": False},
    ).first()
    if rotated is None:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.id == previous.session_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now),
            execution_options={"synchronize_session": False},
        )
        db.commit()
        return invalid_refresh()
    user = db.get(User, rotated.user_id)
    if user is None:
        db.rollback()
        return invalid_refresh()
    db.add(RefreshToken(token_hash=replacement_hash, session_id=rotated.id))
    db.commit()
    set_refresh_cookie(response, replacement, rotated.expires_at)
    return auth_response(user, rotated.id, rotated.expires_at)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser, response: Response) -> User:
    prevent_caching(response)
    return user


@router.post("/logout", status_code=204, dependencies=[Depends(require_trusted_origin)])
def logout(request: Request, db: Database) -> Response:
    token = request.cookies.get(settings.refresh_cookie_name)
    if token and len(token) <= 256:
        db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.id.in_(
                    select(RefreshToken.session_id).where(RefreshToken.token_hash == hash_refresh_token(token))
                ),
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now()),
            execution_options={"synchronize_session": False},
        )
        db.commit()
    response = Response(status_code=204)
    clear_refresh_cookie(response)
    return response


@router.post("/revoke", status_code=204)
def revoke(user: CurrentUser, db: Database) -> Response:
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=utc_now()),
        execution_options={"synchronize_session": False},
    )
    db.commit()
    response = Response(status_code=204)
    clear_refresh_cookie(response)
    return response
