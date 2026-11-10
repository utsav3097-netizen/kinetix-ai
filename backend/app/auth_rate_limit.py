"""Database-atomic fixed-window limits shared by every API worker.

Each endpoint has 4,096 persistent hash slots: storage is capped at 12,288 rows.
Colliding clients share a limit conservatively, and slots reset in place. The
socket peer is used unless a specifically trusted, validated client-IP header is configured.
"""

import ipaddress

import hmac
from collections.abc import Callable

from fastapi import HTTPException, Request
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth import Database
from app.config import settings
from app.models import AuthRateBucket, RefreshSession
from app.models.identity import utc_now

RATE_LIMITS = {"register": (10, 900), "login": (30, 300), "refresh": (120, 300)}
RATE_SLOTS = 4096


def rate_limit(scope: str) -> Callable:
    limit, window_seconds = RATE_LIMITS[scope]

    def enforce(request: Request, db: Database) -> None:
        now = utc_now()
        timestamp = int(now.timestamp())
        window_start = timestamp - timestamp % window_seconds
        if settings.trusted_client_ip_header:
            header_value = request.headers.get(settings.trusted_client_ip_header)
            try:
                peer = str(ipaddress.ip_address(header_value)) if header_value else None
            except ValueError:
                peer = None
            if peer is None:
                raise HTTPException(status_code=503, detail="Trusted client IP is unavailable")
        else:
            peer = request.client.host if request.client is not None else "unknown"
        digest = hmac.digest(settings.jwt_secret.get_secret_value().encode(), peer.encode(), "sha256")
        slot = int.from_bytes(digest[:4], "big") % RATE_SLOTS
        insert = postgres_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = insert(AuthRateBucket).values(
            scope=scope, slot=slot, window_start=window_start, attempts=1
        )
        statement = statement.on_conflict_do_update(
            index_elements=[AuthRateBucket.scope, AuthRateBucket.slot],
            set_={
                "window_start": window_start,
                "attempts": case(
                    (
                        AuthRateBucket.window_start == window_start,
                        case(
                            (AuthRateBucket.attempts >= limit + 1, limit + 1),
                            else_=AuthRateBucket.attempts + 1,
                        ),
                    ),
                    else_=1,
                ),
            },
        ).returning(AuthRateBucket.attempts)
        attempts = db.execute(statement).scalar_one()
        # Replay hashes are retained until absolute expiry, then cascade away.
        db.execute(
            delete(RefreshSession).where(RefreshSession.expires_at <= now),
            execution_options={"synchronize_session": False},
        )
        # Persist even rejected attempts and subsequent credential failures.
        db.commit()
        if attempts > limit:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts. Try again later.",
                headers={
                    "Retry-After": str(window_start + window_seconds - timestamp),
                    "Cache-Control": "no-store",
                },
            )

    return enforce


register_rate_limit = rate_limit("register")
login_rate_limit = rate_limit("login")
refresh_rate_limit = rate_limit("refresh")
