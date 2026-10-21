import pytest
from sqlalchemy import select

from app.auth_security import verify_password
from app import create_user
from app.create_user import UserProvisioningError, provision_user_account
from app.models import User


def test_user_provisioning_normalizes_identity_hashes_password_and_forces_user_role(test_db):
    password = "a sufficiently long user password"
    with test_db() as db:
        user = provision_user_account(db, "  Student@Example.edu ", password)
        stored = db.get(User, user.id)

        assert stored.login_identity == "student@example.edu"
        assert stored.role == "user"
        assert stored.is_active is True
        assert stored.password_hash != password
        assert verify_password(password, stored.password_hash)


def test_user_provisioning_rejects_duplicate_normalized_identity(test_db):
    with test_db() as db:
        user = provision_user_account(db, "Student@Example.edu", "a sufficiently long password")
        with pytest.raises(UserProvisioningError, match="already exists"):
            provision_user_account(db, " student@example.edu ", "another sufficiently long password")

        assert db.scalar(select(User.id).where(User.login_identity == "student@example.edu")) == user.id
        assert db.scalar(select(User).where(User.login_identity == "student@example.edu")).role == "user"


def test_cli_password_mismatch_stops_before_opening_database(monkeypatch, capsys):
    prompts = iter(["student@example.edu"])
    passwords = iter(["first sufficiently long password", "different sufficiently long password"])
    monkeypatch.setattr(create_user, "input", lambda _: next(prompts), raising=False)
    monkeypatch.setattr(create_user, "getpass", lambda _: next(passwords))
    monkeypatch.setattr(create_user, "SessionLocal", lambda: pytest.fail("database must not be opened"))

    with pytest.raises(SystemExit, match="Passwords did not match"):
        create_user.main()

    output = capsys.readouterr()
    assert "first sufficiently long password" not in output.out + output.err
    assert "different sufficiently long password" not in output.out + output.err


def test_user_provisioning_has_no_role_override_parameter(test_db):
    with test_db() as db:
        with pytest.raises(TypeError):
            provision_user_account(db, "student@example.edu", "a sufficiently long password", role="admin")
        assert db.scalar(select(User.id).where(User.login_identity == "student@example.edu")) is None
