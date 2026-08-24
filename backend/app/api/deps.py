"""Shared FastAPI dependencies: DB session, current authenticated user."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.database.models import User
from app.database.session import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_db() -> Session:
    yield from get_session()


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not token:
        raise unauthorized
    email = decode_access_token(token)
    if not email:
        raise unauthorized
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise unauthorized
    return user
