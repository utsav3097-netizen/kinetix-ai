"""Identity records; refresh token values never enter the database."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),)

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RefreshSession(Base):
    """A revocable token family, also identified by the access JWT's sid."""

    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    current_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    """Retained hashes detect replay throughout the family's absolute lifetime."""

    __tablename__ = "refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("refresh_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )


class AuthRateBucket(Base):
    """Fixed hash slots bound storage independently of the number of client IPs."""

    __tablename__ = "auth_rate_buckets"
    __table_args__ = (
        CheckConstraint("scope IN ('register', 'login', 'refresh')", name="ck_auth_rate_scope"),
        CheckConstraint("slot >= 0 AND slot < 4096", name="ck_auth_rate_slot"),
        CheckConstraint("attempts >= 1", name="ck_auth_rate_attempts"),
    )

    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    slot: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
