import pytest
from sqlalchemy import select


def enter_password(monkeypatch, identity, password, confirmation=None):
    replies = iter([password, password if confirmation is None else confirmation])
    monkeypatch.setattr(identity.cli, "getpass", lambda prompt: next(replies))


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def authorization(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_create_user_uses_canonical_admin_grant_and_hidden_password(client, identity, monkeypatch, capsys):
    password = "ninechars"
    enter_password(monkeypatch, identity, password)
    identity.cli.main(["create-user", " BOOTSTRAP.ADMIN@EXAMPLE.COM "])
    output = capsys.readouterr()
    assert password not in output.out + output.err
    with identity.sessions() as db:
        user = db.scalar(select(identity.models.User))
        assert user.email == "bootstrap.admin@example.com"
        assert user.role == "admin"
        assert user.password_hash.startswith("$argon2id$")
        assert identity.auth.password_matches(user.password_hash, password)
        assert db.scalar(select(identity.models.RefreshSession)) is None
    response = login(client, "bootstrap.admin@example.com", password)
    assert response.status_code == 200
    assert client.get("/test/admin", headers=authorization(response)).status_code == 200


def test_create_user_accepts_explicit_server_role(client, identity, monkeypatch):
    enter_password(monkeypatch, identity, identity.password)
    identity.cli.main(["create-user", "appointed@example.com", "--role", "admin"])
    response = login(client, "appointed@example.com", identity.password)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


@pytest.mark.parametrize("password,confirmation", [
    ("short77", None),
    ("x" * 129, None),
    ("valid-password", "different-password"),
])
def test_create_user_rejects_invalid_passwords(identity, monkeypatch, password, confirmation):
    enter_password(monkeypatch, identity, password, confirmation)
    with pytest.raises(SystemExit) as error:
        identity.cli.main(["create-user", "athlete@example.com"])
    assert error.value.code == 2
    with identity.sessions() as db:
        assert db.scalar(select(identity.models.User)) is None


def test_create_user_does_not_overwrite_existing_account(client, identity, monkeypatch):
    enter_password(monkeypatch, identity, identity.password)
    identity.cli.main(["create-user", "athlete@example.com"])
    enter_password(monkeypatch, identity, "replacement-password")
    with pytest.raises(SystemExit):
        identity.cli.main(["create-user", " ATHLETE@EXAMPLE.COM ", "--role", "admin"])
    response = login(client, "athlete@example.com", identity.password)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "user"


def test_set_role_revokes_sessions_and_requires_new_login(client, identity):
    registered = client.post(
        "/api/v1/auth/register", json={"email": "athlete@example.com", "password": identity.password}
    )
    assert client.get("/test/admin", headers=authorization(registered)).status_code == 403
    identity.cli.main(["set-role", " ATHLETE@EXAMPLE.COM ", "admin"])
    assert client.get("/api/v1/auth/me", headers=authorization(registered)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401
    signed_in = login(client, "athlete@example.com", identity.password)
    assert client.get("/test/admin", headers=authorization(signed_in)).status_code == 200
    identity.cli.main(["set-role", "athlete@example.com", "user"])
    assert client.get("/test/admin", headers=authorization(signed_in)).status_code == 401
    assert login(client, "athlete@example.com", identity.password).json()["user"]["role"] == "user"


def test_set_password_revokes_all_sessions_and_preserves_role(client, identity, monkeypatch, capsys):
    registered = client.post(
        "/api/v1/auth/register", json={"email": "bootstrap.admin@example.com", "password": identity.password}
    )
    second = login(client, "bootstrap.admin@example.com", identity.password)
    new_password = "new-strong-password-98"
    enter_password(monkeypatch, identity, new_password)
    identity.cli.main(["set-password", " BOOTSTRAP.ADMIN@EXAMPLE.COM "])
    output = capsys.readouterr()
    assert new_password not in output.out + output.err
    assert client.get("/api/v1/auth/me", headers=authorization(registered)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=authorization(second)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert login(client, "bootstrap.admin@example.com", identity.password).status_code == 401
    signed_in = login(client, "bootstrap.admin@example.com", new_password)
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["role"] == "admin"


@pytest.mark.parametrize("command", ["set-password", "set-role"])
def test_admin_changes_require_existing_account(identity, monkeypatch, command):
    enter_password(monkeypatch, identity, identity.password)
    arguments = [command, "missing@example.com"]
    if command == "set-role":
        arguments.append("admin")
    with pytest.raises(SystemExit) as error:
        identity.cli.main(arguments)
    assert error.value.code == 2
