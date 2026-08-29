import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.rbac import ALL_ROLES


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str
    display_name: str | None = None
    site_id: uuid.UUID | None = None

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


class LoginResponse(BaseModel):
    token: str
    user: UserProfile
