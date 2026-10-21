"""Interactive local CLI for provisioning a normal user account."""

from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth_security import hash_password, normalize_login_identity
from app.database import SessionLocal
from app.models import User


class UserProvisioningError(ValueError):
    """A safe, user-facing provisioning validation error."""


def provision_user_account(db: Session, login_identity: str, password: str) -> User:
    identity = normalize_login_identity(login_identity)
    if not identity or len(identity) > 320:
        raise UserProvisioningError("Login identity must contain 1 to 320 characters.")
    if len(password) < 12 or len(password) > 1024:
        raise UserProvisioningError("Password must contain 12 to 1024 characters.")
    if db.scalar(select(User.id).where(User.login_identity == identity)) is not None:
        raise UserProvisioningError("That login identity already exists; no account was changed.")

    user = User(
        login_identity=identity,
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise UserProvisioningError("That login identity already exists; no account was changed.") from None
    db.refresh(user)
    return user


def main() -> None:
    identity = input("User login identity: ")
    password = getpass("User password (12+ characters): ")
    confirmation = getpass("Confirm user password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no account was created.")

    try:
        with SessionLocal() as db:
            provision_user_account(db, identity, password)
    except UserProvisioningError as exc:
        raise SystemExit(str(exc)) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Could not verify whether account creation completed. Check that the database is "
            "available and the authentication schema has been migrated before retrying."
        ) from None
    print("User account created.")


if __name__ == "__main__":
    main()
