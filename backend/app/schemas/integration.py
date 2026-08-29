import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    integration_id: uuid.UUID
    site_id: uuid.UUID | None
    integration_type: str | None
    name: str | None
    provider: str | None
    version: str | None
    status: str | None
    is_fixed_engine: bool
    last_success_at: datetime | None
    last_error_at: datetime | None
