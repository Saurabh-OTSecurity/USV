import uuid

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.core.rbac import ALL_ROLES


class LoginRequest(BaseModel):
    username: str
    password: str
    # Only meaningful in MULTI_TENANT_POOL mode: which tenant's database to
    # check the username/password against before a JWT (and its tenant_id
    # claim) exists. Ignored in SINGLE_TENANT mode.
    tenant_code: str | None = None


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str
    display_name: str | None = None
    site_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, value: str) -> str:
        if value not in ALL_ROLES:
            raise ValueError(f"role must be one of {ALL_ROLES}")
        return value


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    username: str
    role: str
    display_name: str | None
    site_id: uuid.UUID | None
    business_unit_id: uuid.UUID | None = None
    status: str = "active"
    must_change_password: bool = False
    locked: bool = False

    @model_validator(mode="before")
    @classmethod
    def _locked_from_orm(cls, value):
        if hasattr(value, "locked_at"):
            return {**{k: getattr(value, k, None) for k in (
                "user_id", "username", "role", "display_name", "site_id", "business_unit_id", "status",
                "must_change_password")}, "locked": value.locked_at is not None}
        return value


class LoginResponse(BaseModel):
    token: str
    user: UserProfile
