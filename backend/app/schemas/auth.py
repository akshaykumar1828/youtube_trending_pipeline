"""Authentication and tenant request/response models.

Requests forbid unknown fields, so a browser cannot smuggle in a tenant_id or role: the
tenant always comes from the authenticated session.
"""

import datetime as dt
import re
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.auth.passwords import MAX_PASSWORD_LENGTH, password_problem
from app.auth.permissions import Permission, Role

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value):
        raise ValueError("Enter a valid email address.")
    return value


def _check_password(value: str) -> str:
    problem = password_problem(value)
    if problem:
        raise ValueError(problem)
    return value


Email = Annotated[str, StringConstraints(max_length=320), AfterValidator(_normalize_email)]
NewPassword = Annotated[str, StringConstraints(max_length=1024), AfterValidator(_check_password)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: NewPassword = Field(description="12 to 128 characters.")
    display_name: Name
    tenant_name: Name | None = Field(None, description="Workspace name. Default: '<display_name>'s workspace'.")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    permissions: list[Permission] = Field(description="Derived from the role on the server.")


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str


class CurrentUser(BaseModel):
    user: UserOut
    tenant: TenantOut


class LogoutResult(BaseModel):
    status: Literal["logged_out"]


class TenantDetail(TenantOut):
    created_at: dt.datetime
    member_count: int


class Member(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    is_active: bool
    created_at: dt.datetime
    last_login_at: dt.datetime | None


class CreateMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email
    display_name: Name
    password: NewPassword = Field(description="Initial password (12 to 128 characters); share it securely.")
    role: Role = Role.MEMBER


class UpdateMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    is_active: bool | None = Field(None, description="false signs the user out everywhere and blocks sign-in.")

    @model_validator(mode="after")
    def _not_empty(self):
        if self.role is None and self.is_active is None:
            raise ValueError("Provide role and/or is_active.")
        return self
