"""Interactive server-only account provisioning, roles, and password rotation."""

import argparse
from getpass import getpass

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, password_hasher
from app.config import settings
from app.database import SessionLocal
from app.email_address import canonical_email
from app.models import RefreshSession, User
from app.models.identity import utc_now


def prompt_password_hash(parser: argparse.ArgumentParser) -> str:
    try:
        password = getpass("Password: ")
        confirmation = getpass("Confirm password: ")
    except (EOFError, KeyboardInterrupt):
        parser.error("Password entry cancelled")
    if password != confirmation:
        parser.error("Passwords do not match")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        parser.error(f"Password must contain {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} characters")
    return password_hasher.hash(password)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="KINETIX server administration")
    commands = parser.add_subparsers(dest="command", required=True)
    set_role = commands.add_parser("set-role", help="Assign a role and revoke all existing sessions")
    set_role.add_argument("email", type=canonical_email)
    set_role.add_argument("role", choices=("user", "admin"))
    create_user = commands.add_parser("create-user", help="Pre-provision an account with a hidden password prompt")
    create_user.add_argument("email", type=canonical_email)
    create_user.add_argument("--role", choices=("user", "admin"))
    set_password = commands.add_parser("set-password", help="Rotate a password and revoke all existing sessions")
    set_password.add_argument("email", type=canonical_email)
    arguments = parser.parse_args(argv)
    password_hash = prompt_password_hash(parser) if arguments.command in {"create-user", "set-password"} else None
    try:
        with SessionLocal.begin() as db:
            user = db.scalar(select(User).where(User.email == arguments.email).with_for_update())
            if arguments.command == "create-user":
                if user is not None:
                    parser.error("An account already exists with that email")
                role = arguments.role or ("admin" if arguments.email == settings.admin_email else "user")
                db.add(User(email=arguments.email, password_hash=password_hash, role=role))
            else:
                if user is None:
                    parser.error("No account exists with that email")
                if arguments.command == "set-password":
                    user.password_hash = password_hash
                else:
                    user.role = arguments.role
                db.execute(
                    update(RefreshSession)
                    .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
                    .values(revoked_at=utc_now()),
                    execution_options={"synchronize_session": False},
                )
    except IntegrityError:
        parser.error("Unable to update account; the email may already be registered")
    if arguments.command == "create-user":
        print(f"Account created with role {role}.")
    else:
        print("Account updated; existing sessions revoked.")


if __name__ == "__main__":
    main()
