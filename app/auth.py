import hashlib
import secrets
from typing import Annotated

from fastapi import HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)]


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_auth(
    request: Request,
    credentials: Credentials = None,
) -> None:
    """Resolve the bearer token to a user identity."""
    if not settings.bearer_token:
        # Nothing to authenticate against, so every caller is anonymous and none
        # of them is an admin. Settings rejects this alongside multi-user mode.
        request.state.user_id = settings.default_user_id
        request.state.is_admin = False
        return

    if credentials is None:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    if secrets.compare_digest(
        credentials.credentials.encode(), settings.bearer_token.encode()
    ):
        request.state.user_id = settings.default_user_id
        request.state.is_admin = settings.multi_user_enabled
        return

    if not settings.multi_user_enabled:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    user = request.app.state.db.execute(
        "SELECT id FROM users WHERE token_hash = ?",
        (_token_hash(credentials.credentials),),
    ).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    request.state.user_id = user["id"]
    request.state.is_admin = False


def current_user_id(request: Request) -> int:
    return request.state.user_id


def require_admin(request: Request) -> None:
    if not request.state.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


def require_multi_user() -> None:
    if not settings.multi_user_enabled:
        raise HTTPException(status_code=404, detail="Multi-user mode is disabled")
