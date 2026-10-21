from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from sqlalchemy import select

from app.auth import get_admin_user
from app.auth_security import hash_password, hash_session_token, verify_password
from app.config import Settings
from app.create_admin import AdminProvisioningError, provision_initial_admin
from app.models import AuthSession, User


ORIGIN = "http://localhost:5173"


def add_user(test_db, *, identity="student@example.edu", password="correct horse battery", role="user", active=True):
    with test_db() as db:
        user = User(
            login_identity=identity,
            password_hash=hash_password(password),
            role=role,
            is_active=active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def csrf_headers(client, *, origin=ORIGIN):
    token = client.get("/api/auth/csrf", headers={"Origin": origin}).json()["csrf_token"]
    return {"Origin": origin, "X-CSRF-Token": token}


def test_passwords_are_argon2id_hashes_and_plaintext_is_not_persisted(test_db):
    password = "correct horse battery"
    user_id = add_user(test_db, password=password)
    with test_db() as db:
        stored = db.get(User, user_id).password_hash
    assert stored.startswith("$argon2id$")
    assert stored != password
    assert verify_password(password, stored)
    assert not verify_password("incorrect password", stored)


def test_login_creates_hashed_session_and_returns_only_safe_user_fields(client, test_db):
    user_id = add_user(test_db)
    headers = csrf_headers(client)
    response = client.post(
        "/api/auth/login",
        json={"login_identity": "  STUDENT@Example.edu ", "password": "correct horse battery"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"id": user_id, "login_identity": "student@example.edu", "role": "user"}
    assert set(body) == {"user", "csrf_token"}
    cookie = response.cookies.get("helpdesk_session")
    assert cookie
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    with test_db() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        assert session is not None
        assert session.token_hash == hashlib.sha256(cookie.encode()).hexdigest()
        assert session.token_hash != cookie


def test_invalid_login_is_generic_for_missing_user_and_bad_password(client):
    headers = csrf_headers(client)
    missing = client.post("/api/auth/login", json={"login_identity": "missing@example.edu", "password": "incorrect password"}, headers=headers)
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Invalid login identity or password."


def test_existing_user_bad_password_and_inactive_account_are_rejected_generically(client, test_db):
    add_user(test_db, active=True)
    add_user(test_db, identity="inactive@example.edu", active=False)
    headers = csrf_headers(client)
    wrong = client.post("/api/auth/login", json={"login_identity": "student@example.edu", "password": "bad password"}, headers=headers)
    inactive = client.post("/api/auth/login", json={"login_identity": "inactive@example.edu", "password": "correct horse battery"}, headers=headers)
    assert wrong.status_code == inactive.status_code == 401
    assert wrong.json() == inactive.json() == {"detail": "Invalid login identity or password."}


def test_me_requires_valid_active_unexpired_session_and_returns_safe_fields(client, test_db):
    user_id = add_user(test_db)
    assert client.get("/api/auth/me").status_code == 401
    client.post("/api/auth/login", json={"login_identity": "student@example.edu", "password": "correct horse battery"}, headers=csrf_headers(client))
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {"id": user_id, "login_identity": "student@example.edu", "role": "user"}

    with test_db() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    with test_db() as db:
        assert db.scalar(select(AuthSession).where(AuthSession.user_id == user_id)).revoked_at is not None


def test_deactivated_user_session_is_revoked_on_next_request(client, test_db):
    user_id = add_user(test_db)
    client.post("/api/auth/login", json={"login_identity": "student@example.edu", "password": "correct horse battery"}, headers=csrf_headers(client))
    with test_db() as db:
        db.get(User, user_id).is_active = False
        db.commit()
    assert client.get("/api/auth/me").status_code == 401
    with test_db() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        assert session.revoked_at is not None


def test_revoked_session_is_rejected(client, test_db):
    user_id = add_user(test_db)
    client.post("/api/auth/login", json={"login_identity": "student@example.edu", "password": "correct horse battery"}, headers=csrf_headers(client))
    with test_db() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_session_and_clears_cookies(client, test_db):
    user_id = add_user(test_db)
    login = client.post("/api/auth/login", json={"login_identity": "student@example.edu", "password": "correct horse battery"}, headers=csrf_headers(client))
    csrf_token = login.json()["csrf_token"]
    response = client.post("/api/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token})
    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    assert 'helpdesk_session=""' in response.headers["set-cookie"]
    assert 'helpdesk_csrf=""' in response.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 401
    with test_db() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        assert session.revoked_at is not None


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.example", "X-CSRF-Token": "x"},
        {"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
    ],
)
def test_login_rejects_missing_or_invalid_origin_and_csrf(client, headers):
    client.get("/api/auth/csrf", headers={"Origin": ORIGIN})
    response = client.post("/api/auth/login", json={"login_identity": "x", "password": "x"}, headers=headers)
    assert response.status_code == 403


def test_csrf_token_issue_rejects_unconfigured_origin(client):
    response = client.get("/api/auth/csrf", headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403


def test_cors_settings_require_explicit_origins_and_https_in_production():
    with pytest.raises(ValueError, match="wildcard"):
        Settings(cors_origins="*").allowed_origins
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(app_env="production", cors_origins="http://localhost:5173").allowed_origins
    assert Settings(cors_origins="http://localhost:5173,http://127.0.0.1:5173").allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_logout_requires_csrf_and_origin(client):
    assert client.post("/api/auth/logout").status_code == 403


def test_csrf_token_is_rotated_on_login(client, test_db):
    add_user(test_db)
    original_token = client.get("/api/auth/csrf", headers={"Origin": ORIGIN}).json()["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"login_identity": "student@example.edu", "password": "correct horse battery"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": original_token},
    )
    assert response.status_code == 200
    assert response.json()["csrf_token"] != original_token
    assert response.cookies.get("helpdesk_csrf") == response.json()["csrf_token"]


def test_cors_allows_explicit_frontend_origin_with_credentials(client):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "x-csrf-token" in response.headers["access-control-allow-headers"].lower()


def test_cors_does_not_allow_unconfigured_origin(client):
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_admin_provisioning_hashes_password_and_rejects_duplicate_normalized_identity(test_db):
    with test_db() as db:
        admin = provision_initial_admin(db, "  Admin@Example.edu ", "a sufficiently long password")
        assert admin.login_identity == "admin@example.edu"
        assert admin.role == "admin"
        assert admin.password_hash != "a sufficiently long password"
        assert verify_password("a sufficiently long password", admin.password_hash)
        with pytest.raises(AdminProvisioningError, match="already exists"):
            provision_initial_admin(db, "ADMIN@example.edu", "another sufficiently long password")
        assert db.scalar(select(User).where(User.login_identity == "admin@example.edu")).id == admin.id


def test_admin_dependency_rejects_users_and_accepts_admins(test_db):
    with test_db() as db:
        user = User(login_identity="user@example.edu", password_hash=hash_password("long enough password"), role="user")
        admin = User(login_identity="admin@example.edu", password_hash=hash_password("long enough password"), role="admin")
        db.add_all([user, admin])
        db.commit()
        with pytest.raises(Exception) as error:
            get_admin_user(user)
        assert getattr(error.value, "status_code", None) == 403
        assert get_admin_user(admin).role == "admin"


def test_session_token_hash_is_sha256_only():
    token = "random-session-token"
    assert hash_session_token(token) == hashlib.sha256(token.encode()).hexdigest()
