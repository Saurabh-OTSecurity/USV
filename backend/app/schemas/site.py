import uuid

from pydantic import BaseModel, ConfigDict


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: uuid.UUID
    site_code: str
    name: str
    description: str | None
    timezone: str | None
    criticality: str | None
    status: str | None
