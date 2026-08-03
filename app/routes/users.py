from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth import current_user_id, require_admin
from app.config import settings
from app.models.user import User, UserCreate, UserWithToken
from app.repositories.users import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


def _repo(request: Request) -> UserRepository:
    return UserRepository(request.app.state.db)


@router.get("/me", response_model=User, summary="Get current user")
def get_current_user(request: Request):
    user = _repo(request).get(current_user_id(request))
    assert user is not None
    return user


@router.get(
    "", response_model=list[User], dependencies=[Depends(require_admin)], summary="List users"
)
def list_users(request: Request):
    return _repo(request).list_all()


@router.post(
    "",
    response_model=UserWithToken,
    status_code=201,
    dependencies=[Depends(require_admin)],
    summary="Create user",
)
def create_user(request: Request, body: UserCreate):
    user, token = _repo(request).create(body.name.strip())
    return {**user, "token": token}


@router.post(
    "/{user_id}/token",
    response_model=UserWithToken,
    dependencies=[Depends(require_admin)],
    summary="Rotate user token",
)
def rotate_user_token(request: Request, user_id: int):
    if user_id == settings.default_user_id:
        # require_auth matches NT_BEARER_TOKEN before consulting token_hash, so a
        # rotated default-user token would authenticate as a non-admin while the
        # env var kept full access. Rotate the env var instead.
        raise HTTPException(
            status_code=409,
            detail="The default user authenticates with NT_BEARER_TOKEN; rotate that instead",
        )
    result = _repo(request).rotate_token(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    user, token = result
    return {**user, "token": token}
