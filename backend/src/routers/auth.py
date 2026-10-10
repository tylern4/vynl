from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..config import settings
from ..database import get_db
from ..models import Role, User, UserStatus
from ..schemas import LoginRequest, RegisterOut, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Annotated[Session, Depends(get_db)]):
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists"
        )
    # The invite code bootstraps the instance: it is required only to create
    # the very first account (which becomes admin+active). Later sign-ups
    # register freely and land in `pending` until an admin approves them.
    is_first = (db.scalar(select(func.count(User.id))) or 0) == 0
    if is_first and payload.invite_code != settings.invite_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid invite code"
        )
    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=Role.admin if is_first else Role.user,
        status=UserStatus.active if is_first else UserStatus.pending,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user) if user.status == UserStatus.active else None
    return RegisterOut(user=UserOut.model_validate(user), access_token=token)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    if user.status == UserStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is awaiting approval by an admin.",
        )
    if user.status == UserStatus.denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account was denied by an admin.",
        )
    return TokenOut(access_token=create_access_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
