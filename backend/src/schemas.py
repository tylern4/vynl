from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Role, UserStatus


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite_code: str | None = Field(default=None, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: Role
    status: UserStatus


class UserAdminOut(UserOut):
    created_at: datetime


class RegisterOut(BaseModel):
    user: UserOut
    access_token: str | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RoleUpdate(BaseModel):
    role: Role


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    status: UserStatus | None = None
    role: Role | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
