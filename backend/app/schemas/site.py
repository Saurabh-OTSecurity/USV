import uuid

from pydantic import BaseModel, ConfigDict


class SiteCreate(BaseModel):
    site_code: str
    name: str
    business_unit_id: uuid.UUID
    description: str | None = None
    timezone: str | None = None
    criticality: str | None = None
    # where people open this site's Tribot (single sign-on from USV)
    tribot_url: str | None = None


class SiteTribotUrl(BaseModel):
    tribot_url: str | None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: uuid.UUID
    business_unit_id: uuid.UUID
    site_code: str
    name: str
    description: str | None
    timezone: str | None
    criticality: str | None
    status: str | None
    tribot_url: str | None = None
