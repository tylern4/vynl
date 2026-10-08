from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import get_admin_user, hash_password
from ..database import get_db
from ..models import Role, User, UserStatus
from ..schemas import PasswordReset, RoleUpdate, UserAdminOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _apply_status(db: Session, admin: User, user: User, new_status: UserStatus) -> User:
    if new_status == UserStatus.denied and user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deny your own account"
        )
    user.status = new_status
    db.commit()
    db.refresh(user)
    return user


def _apply_role(db: Session, user: User, new_role: Role) -> User:
    if user.role == Role.admin and new_role != Role.admin:
        admin_count = db.scalar(select(func.count(User.id)).where(User.role == Role.admin)) or 0
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last admin",
            )
    user.role = new_role
    db.commit()
    db.refresh(user)
    return user


def _apply_password(db: Session, user: User, password: str) -> User:
    user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserAdminOut])
def list_users(
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(select(User).order_by(User.created_at.asc(), User.id.asc())).all()


@router.patch("/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(db, user_id)
    if payload.status is not None:
        user = _apply_status(db, admin, user, payload.status)
    if payload.role is not None:
        user = _apply_role(db, user, payload.role)
    if payload.password is not None:
        user = _apply_password(db, user, payload.password)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    user = _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account"
        )
    db.delete(user)
    db.commit()


@router.post("/{user_id}/approve", response_model=UserAdminOut)
def approve_user(
    user_id: int,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return _apply_status(db, admin, _get_user(db, user_id), UserStatus.active)


@router.post("/{user_id}/deny", response_model=UserAdminOut)
def deny_user(
    user_id: int,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return _apply_status(db, admin, _get_user(db, user_id), UserStatus.denied)


@router.patch("/{user_id}/role", response_model=UserAdminOut)
def set_user_role(
    user_id: int,
    payload: RoleUpdate,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return _apply_role(db, _get_user(db, user_id), payload.role)


@router.post("/{user_id}/reset-password", response_model=UserAdminOut)
def reset_user_password(
    user_id: int,
    payload: PasswordReset,
    admin: Annotated[User, Depends(get_admin_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return _apply_password(db, _get_user(db, user_id), payload.password)
