"""Behavioral tests migrate a fresh temporary SQLite database, never live data."""

from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

TEST_SECRET = "isolated-auth-tests-5uG9wQ7rN2vX4sP8dK6bL1mC"
TEST_PASSWORD = "a-long-test-password-42"


@pytest.fixture
def identity(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'identity.sqlite').as_posix()}"
    # Set the database environment BEFORE importing any application module.
    # No application global engine can accidentally point at a deployed DB.
    values = {
        "APP_ENV": "local",
        "DATABASE_URL": database_url,
        "JWT_SECRET": TEST_SECRET,
        "ADMIN_EMAIL": "bootstrap.admin@example.com",
        "CORS_ORIGINS": '["https://client.example.com"]',
        "REFRESH_COOKIE_NAME": "kinetix_refresh",
        "ACCESS_TOKEN_MINUTES": "15",
        "REFRESH_TOKEN_DAYS": "30",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    from app import auth, auth_rate_limit, auth_routes, cli, config, database, models
    from app.errors import request_validation_error

    test_settings = config.Settings(_env_file=None)
    for module in (config, auth, auth_rate_limit, auth_routes, cli):
        monkeypatch.setattr(module, "settings", test_settings)
    command.upgrade(Config(str(config.BACKEND_DIR / "alembic.ini")), "head")

    engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(cli, "SessionLocal", sessions)

    def get_test_db():
        with sessions() as session:
            yield session

    app = FastAPI()
    app.add_exception_handler(RequestValidationError, request_validation_error)
    app.include_router(auth_routes.router)
    app.dependency_overrides[database.get_db] = get_test_db

    @app.get("/test/admin")
    def admin_only(user=Depends(auth.require_admin)):
        assert isinstance(user, models.User)
        return {"id": user.id, "role": user.role}

    yield SimpleNamespace(
        app=app,
        sessions=sessions,
        settings=test_settings,
        auth=auth,
        rates=auth_rate_limit,
        models=models,
        cli=cli,
        password=TEST_PASSWORD,
    )
    engine.dispose()


@pytest.fixture
def client(identity):
    with TestClient(identity.app, base_url="http://testserver", headers={"Origin": "http://testserver"}) as client:
        yield client
