"""Password and opaque-session-token primitives for the authentication API."""

import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError


_password_hash = PasswordHash.recommended()
# A real Argon2 hash keeps unknown-login attempts on a similar verification path.
DUMMY_PASSWORD_HASH = _password_hash.hash("not-a-valid-helpdesk-password")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except (PwdlibError, ValueError, TypeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_login_identity(identity: str) -> str:
    return identity.strip().casefold()
