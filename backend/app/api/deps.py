"""Auth dependencies: current user + role gates."""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.deps import get_db
from app.db.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc
    user_id = payload.get("uid")
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    # The token must name the same wallet as the user row; a token carrying only a uid
    # (e.g. forged for the admin's id) is rejected.
    sub = payload.get("sub")
    if not isinstance(sub, str) or sub.lower() != user.address.lower():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return user


def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_access_token(creds.credentials)
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc
    user_id = payload.get("uid")
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return user

    return _dep


require_admin = require_roles(UserRole.admin)
require_operator = require_roles(UserRole.admin, UserRole.operator)
require_participant = require_roles(UserRole.admin, UserRole.operator, UserRole.participant)
