"""Phase 13: real authentication for the login gate the user chose to keep (spec itself never
requires accounts). Register + login + "who am I" against a real, persisted user table --
replacing Phase 1's frontend-only stub that accepted any input."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.auth.security import create_access_token, hash_password, verify_password
from app.config import NOT_LIVE_TRADING_DISCLAIMER
from app.database.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    return TokenResponse(access_token=create_access_token(subject=user.email))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user or not verify_password(payload.password, user.hashed_password):
        raise invalid
    return TokenResponse(access_token=create_access_token(subject=user.email))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=current_user.id, email=current_user.email)


@router.get("/disclaimer")
def disclaimer() -> dict:
    """Unauthenticated -- lets the frontend show the not-live-trading disclaimer before login."""
    return {"disclaimer": NOT_LIVE_TRADING_DISCLAIMER}
