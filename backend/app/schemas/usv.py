import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UsvResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usv_id: uuid.UUID
    site_id: uuid.UUID
    usv_code: str
    hostname: str | None
    installation_id: str | None
    version: str | None
    status: str | None
    last_heartbeat: datetime | None
