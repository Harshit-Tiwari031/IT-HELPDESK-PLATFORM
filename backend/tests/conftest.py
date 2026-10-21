import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models  # noqa: F401 - import models before creating test schema
from app.auth_security import hash_password
from app.models import User


TEST_ORIGIN = "http://localhost:5173"


class CSRFTestClient(TestClient):
    """Test browser requests, adding Origin and the double-submit token automatically."""

    def request(self, method, url, *args, **kwargs):
        if method.upper() in {"POST", "PATCH", "PUT", "DELETE"}:
            headers = dict(kwargs.get("headers") or {})
            headers.setdefault("Origin", TEST_ORIGIN)
            csrf_token = self.cookies.get("helpdesk_csrf")
            if csrf_token:
                headers.setdefault("X-CSRF-Token", csrf_token)
            kwargs["headers"] = headers
        return super().request(method, url, *args, **kwargs)


def _login_test_account(test_db, test_client, identity, role):
    with test_db() as db:
        user = User(login_identity=identity, password_hash=hash_password("isolated test password"), role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    csrf = test_client.get("/api/auth/csrf", headers={"Origin": TEST_ORIGIN}).json()["csrf_token"]
    response = test_client.post(
        "/api/auth/login",
        json={"login_identity": identity, "password": "isolated test password"},
        headers={"Origin": TEST_ORIGIN, "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    test_client.auth_user_id = user_id


@pytest.fixture
def test_db():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        with TestingSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSessionLocal
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(test_db):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client(client):
    return client


@pytest.fixture
def user_client(test_db):
    with CSRFTestClient(app) as test_client:
        _login_test_account(test_db, test_client, "user@example.edu", "user")
        yield test_client


@pytest.fixture
def admin_client(test_db):
    with CSRFTestClient(app) as test_client:
        _login_test_account(test_db, test_client, "admin@example.edu", "admin")
        yield test_client
