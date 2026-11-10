import hmac
import ipaddress

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update


def register(client, identity, email="athlete@example.com", **extra):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": identity.password, **extra},
    )


def bearer(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def cookie_header(identity, token):
    return {"Cookie": f"{identity.settings.refresh_cookie_name}={token}"}


def test_migrations_initialize_foundation_and_empty_users(identity):
    with identity.sessions() as db:
        assert db.scalar(select(identity.models.SystemSchema.component)) == "kinetix-ai"
        assert db.scalar(select(func.count()).select_from(identity.models.User)) == 0


def test_canonical_registration_login_and_password_hash(client, identity):
    registered = register(client, identity, "  Straße@EXAMPLE.COM  ")
    assert registered.status_code == 201
    data = registered.json()
    assert data["user"]["email"] == "strasse@example.com"
    assert data["user"]["role"] == "user"
    assert str(UUID(data["user"]["id"])) == data["user"]["id"]
    assert data["token_type"] == "bearer"
    assert set(data) == {"access_token", "token_type", "user"}
    with identity.sessions() as db:
        user = db.scalar(select(identity.models.User))
        assert user.password_hash.startswith("$argon2id$")
        assert identity.auth.password_matches(user.password_hash, identity.password)
        assert user.password_hash != identity.password
    logged_in = client.post(
        "/api/v1/auth/login",
        json={"email": "  STRASSE@example.com ", "password": identity.password},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["user"] == data["user"]
    me = client.get("/api/v1/auth/me", headers=bearer(logged_in))
    assert me.status_code == 200
    assert me.json() == data["user"]
    assert register(client, identity, "STRASSE@EXAMPLE.COM").status_code == 409


def test_credentials_errors_do_not_reveal_account_presence(client, identity):
    assert register(client, identity).status_code == 201
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "athlete@example.com", "password": "wrong-password"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "unknown@example.com", "password": "wrong-password"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


@pytest.mark.parametrize("extra", [{"role": "admin"}, {"is_admin": True}, {"user": {"role": "admin"}}])
def test_registration_rejects_role_escalation(client, identity, extra):
    assert register(client, identity, **extra).status_code == 422
    with identity.sessions() as db:
        assert db.scalar(select(func.count()).select_from(identity.models.User)) == 0


@pytest.mark.parametrize("password", ["short77", "x" * 129])
def test_registration_enforces_shared_password_bounds(client, identity, password):
    assert register(client, identity, password=password).status_code == 422


@pytest.mark.parametrize("password", ["eight888", "ninechars", "x" * 128])
def test_registration_accepts_password_policy_boundaries(client, identity, password):
    assert register(client, identity, password=password).status_code == 201


def test_registration_rejects_invalid_email(client, identity):
    assert register(client, identity, "not an email").status_code == 422


def test_admin_grant_is_server_only_and_role_is_checked_in_database(client, identity):
    user = register(client, identity)
    assert client.get("/test/admin").status_code == 401
    assert client.get("/test/admin", headers=bearer(user)).status_code == 403
    claims = jwt.decode(
        user.json()["access_token"],
        identity.settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        audience=identity.auth.JWT_AUDIENCE,
        issuer=identity.auth.JWT_ISSUER,
    )
    claims["role"] = "admin"
    forged_role = jwt.encode(claims, identity.settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert client.get("/test/admin", headers={"Authorization": f"Bearer {forged_role}"}).status_code == 403
    admin = register(client, identity, " BOOTSTRAP.ADMIN@EXAMPLE.COM ")
    assert admin.status_code == 201
    assert admin.json()["user"]["role"] == "admin"
    assert client.get("/test/admin", headers=bearer(admin)).status_code == 200
    with identity.sessions.begin() as db:
        db.execute(update(identity.models.User).where(identity.models.User.id == admin.json()["user"]["id"]).values(role="user"))
    assert client.get("/test/admin", headers=bearer(admin)).status_code == 403


def test_cookie_flags_token_claims_and_hash_only_storage(client, identity):
    response = register(client, identity)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in cookie
    assert "Secure" not in cookie
    assert response.headers["cache-control"] == "no-store"
    token = client.cookies.get(identity.settings.refresh_cookie_name)
    assert len(token) == 64
    with identity.sessions() as db:
        session = db.scalar(select(identity.models.RefreshSession))
        history = db.scalar(select(identity.models.RefreshToken))
        assert session.current_token_hash == history.token_hash == identity.auth.hash_refresh_token(token)
        assert session.current_token_hash != token
        claims = jwt.decode(
            response.json()["access_token"],
            identity.settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=identity.auth.JWT_AUDIENCE,
            issuer=identity.auth.JWT_ISSUER,
        )
        assert claims["sid"] == session.id
        assert claims["sub"] == response.json()["user"]["id"]
        assert 0 < claims["exp"] - claims["iat"] <= 15 * 60
        assert claims["type"] == "access"
        assert "role" not in claims


def test_nonlocal_cookie_is_secure(client, identity, monkeypatch):
    monkeypatch.setattr(identity.settings, "app_env", "production")
    assert "Secure" in register(client, identity).headers["set-cookie"]


def test_refresh_rotation_replay_revokes_entire_family(client, identity):
    registered = register(client, identity)
    original = client.cookies.get(identity.settings.refresh_cookie_name)
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    replacement = client.cookies.get(identity.settings.refresh_cookie_name)
    assert original != replacement
    assert refreshed.json()["user"] == registered.json()["user"]
    assert client.get("/api/v1/auth/me", headers=bearer(registered)).status_code == 200
    with identity.sessions() as db:
        assert db.scalar(select(func.count()).select_from(identity.models.RefreshSession)) == 1
        assert db.scalar(select(func.count()).select_from(identity.models.RefreshToken)) == 2
    replay = client.post("/api/v1/auth/refresh", headers=cookie_header(identity, original))
    assert replay.status_code == 401
    assert "Max-Age=0" in replay.headers["set-cookie"]
    assert client.get("/api/v1/auth/me", headers=bearer(registered)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(refreshed)).status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=cookie_header(identity, replacement)).status_code == 401


def test_parallel_refresh_has_one_winner_and_replay_revokes_it(client, identity):
    register(client, identity)
    original = client.cookies.get(identity.settings.refresh_cookie_name)

    def rotate():
        with TestClient(identity.app, headers={"Origin": "http://testserver"}) as peer:
            return peer.post("/api/v1/auth/refresh", headers=cookie_header(identity, original))

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 401]
    winner = next(response for response in responses if response.status_code == 200)
    assert client.get("/api/v1/auth/me", headers=bearer(winner)).status_code == 401


def test_refresh_without_cookie_or_unknown_cookie_is_unauthorized(client, identity):
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=cookie_header(identity, "invalid-token")).status_code == 401


def test_logout_revokes_cookie_family_and_access(client, identity):
    registered = register(client, identity)
    original = client.cookies.get(identity.settings.refresh_cookie_name)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/v1/auth/me", headers=bearer(registered)).status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=cookie_header(identity, original)).status_code == 401
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_revoke_invalidates_all_users_sessions_not_other_users(client, identity):
    first = register(client, identity)
    second = client.post("/api/v1/auth/login", json={"email": "athlete@example.com", "password": identity.password})
    second_cookie = client.cookies.get(identity.settings.refresh_cookie_name)
    other = register(client, identity, "other@example.com")
    assert client.post("/api/v1/auth/revoke").status_code == 401
    assert client.post("/api/v1/auth/revoke", headers=bearer(first)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=bearer(first)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(second)).status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=cookie_header(identity, second_cookie)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(other)).status_code == 200


def test_expired_sessions_reject_access_and_refresh_and_prune_history(client, identity):
    registered = register(client, identity)
    with identity.sessions.begin() as db:
        db.execute(update(identity.models.RefreshSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    assert client.get("/api/v1/auth/me", headers=bearer(registered)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401
    with identity.sessions() as db:
        assert db.scalar(select(func.count()).select_from(identity.models.RefreshSession)) == 0
        assert db.scalar(select(func.count()).select_from(identity.models.RefreshToken)) == 0


@pytest.mark.parametrize("mutation", ["expired", "missing_sid", "wrong_type", "unsigned", "wrong_signature"])
def test_invalid_access_jwts_are_unauthorized(client, identity, mutation):
    registered = register(client, identity)
    claims = jwt.decode(registered.json()["access_token"], options={"verify_signature": False})
    key = identity.settings.jwt_secret.get_secret_value()
    algorithm = "HS256"
    if mutation == "expired":
        claims["exp"] = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    elif mutation == "missing_sid":
        del claims["sid"]
    elif mutation == "wrong_type":
        claims["type"] = "refresh"
    elif mutation == "unsigned":
        key, algorithm = None, "none"
    else:
        key = "different-test-signing-secret-1234567890"
    token = jwt.encode(claims, key, algorithm=algorithm)
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


@pytest.mark.parametrize("endpoint", ["register", "login", "refresh", "logout"])
def test_cookie_endpoints_reject_cross_site_and_missing_origin(identity, endpoint):
    body = {"email": "athlete@example.com", "password": identity.password}
    with TestClient(identity.app) as client:
        assert client.post(f"/api/v1/auth/{endpoint}", json=body).status_code == 403
        assert client.post(
            f"/api/v1/auth/{endpoint}", json=body,
            headers={"Origin": "https://attacker.example.com", "Sec-Fetch-Site": "cross-site"},
        ).status_code == 403
        assert client.post(
            f"/api/v1/auth/{endpoint}", json=body,
            headers={"Origin": "null", "Sec-Fetch-Site": "same-origin"},
        ).status_code == 403


@pytest.mark.parametrize("headers", [
    {"Origin": "https://client.example.com", "Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-origin"},
    {"Referer": "http://testserver/account"},
])
def test_trusted_cookie_request_origins_are_accepted(identity, headers):
    with TestClient(identity.app, headers=headers) as client:
        assert register(client, identity).status_code == 201


def test_rejected_csrf_does_not_rotate_or_revoke_session(client, identity):
    registered = register(client, identity)
    original = client.cookies.get(identity.settings.refresh_cookie_name)
    assert client.post("/api/v1/auth/refresh", headers={"Origin": "https://attacker.example.com"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"Origin": "https://attacker.example.com"}).status_code == 403
    assert client.cookies.get(identity.settings.refresh_cookie_name) == original
    assert client.get("/api/v1/auth/me", headers=bearer(registered)).status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 200


def test_persistent_atomic_rate_bucket_caps_and_resets(client, identity, monkeypatch):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(identity.rates, "utc_now", lambda: now)
    assert client.post("/api/v1/auth/refresh").status_code == 401
    with identity.sessions.begin() as db:
        bucket = db.scalar(select(identity.models.AuthRateBucket))
        assert 0 <= bucket.slot < 4096
        bucket.attempts = 119

    def attempt():
        with TestClient(identity.app, headers={"Origin": "http://testserver"}) as peer:
            return peer.post("/api/v1/auth/refresh")

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: attempt(), range(4)))
    assert sorted(response.status_code for response in responses) == [401, 429, 429, 429]
    assert all(response.headers["retry-after"] == "300" for response in responses if response.status_code == 429)
    with identity.sessions() as db:
        bucket = db.scalar(select(identity.models.AuthRateBucket))
        assert bucket.attempts == 121
        assert db.scalar(select(func.count()).select_from(identity.models.AuthRateBucket)) == 1
    monkeypatch.setattr(identity.rates, "utc_now", lambda: now + timedelta(minutes=5))
    assert client.post("/api/v1/auth/refresh").status_code == 401
    with identity.sessions() as db:
        assert db.scalar(select(identity.models.AuthRateBucket.attempts)) == 1


@pytest.mark.parametrize("endpoint", ["register", "login"])
def test_login_and_registration_are_rate_limited(client, identity, monkeypatch, endpoint):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(identity.rates, "utc_now", lambda: now)
    body = {"email": "not-an-address", "password": identity.password}
    assert client.post(f"/api/v1/auth/{endpoint}", json=body).status_code == 422
    with identity.sessions.begin() as db:
        bucket = db.scalar(select(identity.models.AuthRateBucket).where(identity.models.AuthRateBucket.scope == endpoint))
        bucket.attempts = identity.rates.RATE_LIMITS[endpoint][0]
    assert client.post(f"/api/v1/auth/{endpoint}", json=body).status_code == 429

def test_rate_limit_ignores_untrusted_ip_header_and_requires_trusted_header(client, identity, monkeypatch):
    body = {"email": "limit-check@example.com", "password": identity.password}
    assert client.post(
        "/api/v1/auth/login", json=body, headers={"X-Kinetix-Client-IP": "198.51.100.10"}
    ).status_code == 401
    assert client.post(
        "/api/v1/auth/login", json=body, headers={"X-Kinetix-Client-IP": "203.0.113.20"}
    ).status_code == 401
    with identity.sessions() as db:
        bucket = db.scalar(select(identity.models.AuthRateBucket))
        assert bucket.attempts == 2

    monkeypatch.setattr(identity.settings, "trusted_client_ip_header", "x-kinetix-client-ip")
    assert client.post("/api/v1/auth/login", json=body).status_code == 503
    assert client.post(
        "/api/v1/auth/login", json=body, headers={"X-Kinetix-Client-IP": "not-an-ip"}
    ).status_code == 503
    assert client.post(
        "/api/v1/auth/login", json=body, headers={"X-Kinetix-Client-IP": "198.51.100.10"}
    ).status_code == 401
    peer_ip = str(ipaddress.ip_address("198.51.100.10"))
    expected_digest = hmac.digest(
        identity.settings.jwt_secret.get_secret_value().encode(), peer_ip.encode(), "sha256"
    )
    expected_slot = int.from_bytes(expected_digest[:4], "big") % identity.rates.RATE_SLOTS
    with identity.sessions() as db:
        bucket = db.scalar(
            select(identity.models.AuthRateBucket).where(
                identity.models.AuthRateBucket.scope == "login",
                identity.models.AuthRateBucket.slot == expected_slot,
            )
        )
        assert bucket is not None and bucket.attempts == 1
