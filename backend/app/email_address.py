"""One canonical email representation for configuration, API input, and the CLI."""

from email_validator import EmailNotValidError, validate_email


def canonical_email(value: str) -> str:
    try:
        address = validate_email(value.strip().casefold(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise ValueError("Enter a valid email address") from exc
    return address.normalized.casefold()
