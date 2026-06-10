import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.users.models import UserRole

_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    invite_token: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be at least 8 characters and contain "
                "uppercase, lowercase, and a digit"
            )
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # seconds


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be at least 8 characters and contain "
                "uppercase, lowercase, and a digit"
            )
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class UserAdminResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateRoleRequest(BaseModel):
    role: UserRole


class UpdateActiveRequest(BaseModel):
    is_active: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be at least 8 characters and contain "
                "uppercase, lowercase, and a digit"
            )
        return v


class InviteRequest(BaseModel):
    email: EmailStr
    role: UserRole


class InviteResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitePreviewResponse(BaseModel):
    email: str
    role: UserRole
