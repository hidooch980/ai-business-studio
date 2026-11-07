from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


EmailInput = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
PasswordInput = Annotated[str, StringConstraints(min_length=12, max_length=256)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
TenantName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
TenantSlug = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9-]*$")]


class RegisterRequest(BaseModel):
    email: EmailInput
    password: PasswordInput
    display_name: DisplayName
    tenant_name: TenantName
    tenant_slug: TenantSlug


class LoginRequest(BaseModel):
    email: EmailInput
    password: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str


class MembershipResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str


class AuthContextResponse(BaseModel):
    user: UserResponse
    memberships: list[MembershipResponse] = Field(default_factory=list)
