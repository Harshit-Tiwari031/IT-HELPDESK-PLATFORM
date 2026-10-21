"""Interactive local CLI for provisioning an initial administrator."""

from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_security import hash_password, normalize_login_identity
from app.database import SessionLocal
from app.models import User


class AdminProvisioningError(ValueError):
    pass


def provision_initial_admin(db: Session, login_identity: str, password: str) -> User:
    identity = normalize_login_identity(login_identity)
    if not identity or len(identity) > 320:
        raise AdminProvisioningError("Login identity must contain 1 to 320 characters.")
    if len(password) < 12 or len(password) > 1024:
        raise AdminProvisioningError("Password must contain 12 to 1024 characters.")
    if db.scalar(select(User.id).where(User.login_identity == identity)) is not None:
        raise AdminProvisioningError("That login identity already exists; no account was changed.")

    user = User(login_identity=identity, password_hash=hash_password(password), role="admin", is_active=True)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AdminProvisioningError("That login identity already exists; no account was changed.") from None
    db.refresh(user)
    return user


def main() -> None:
    identity = input("Admin login identity: ").strip()
    password = getpass("Admin password (12+ characters): ")
    confirmation = getpass("Confirm admin password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no account was created.")
    try:
        with SessionLocal() as db:
            provision_initial_admin(db, identity, password)
    except AdminProvisioningError as exc:
        raise SystemExit(str(exc)) from None
    print("Administrator account created.")


if __name__ == "__main__":
    main()
