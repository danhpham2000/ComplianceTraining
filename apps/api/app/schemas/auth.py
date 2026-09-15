from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ActorSummary


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str
    password: str = Field(min_length=8, max_length=128)
    role: Literal["ADMIN", "MANAGER", "EMPLOYEE"] = "EMPLOYEE"


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6)


class ResendVerificationRequest(BaseModel):
    email: str


class PendingVerificationOut(BaseModel):
    message: str
    email: str
    verification_expires_at: datetime
    verification_code_hint: str | None = None


class SessionOut(BaseModel):
    token: str
    actor: ActorSummary


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateDirectoryUserRequest(BaseModel):
    role: Literal["ADMIN", "MANAGER", "EMPLOYEE"] | None = None
    status: Literal["ACTIVE", "INACTIVE"] | None = None


class InviteMemberRequest(BaseModel):
    email: str
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Literal["ADMIN", "MANAGER", "EMPLOYEE"] = "EMPLOYEE"


class UserPreferencesOut(BaseModel):
    time_zone: str | None = None


class UpdatePreferencesRequest(BaseModel):
    time_zone: str | None = Field(default=None, max_length=80)


class WorkspacePreferencesOut(BaseModel):
    ai_script_profile_name: str | None = None
    ai_script_markdown: str | None = None


class UpdateWorkspacePreferencesRequest(BaseModel):
    ai_script_profile_name: str | None = Field(default=None, max_length=255)
    ai_script_markdown: str | None = Field(default=None, max_length=40000)
