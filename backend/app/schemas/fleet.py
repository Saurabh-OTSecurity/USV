import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FleetAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    site_id: uuid.UUID
    source_system: str
    source_asset_id: str
    name: str | None
    device_type: str | None
    risk_level: str | None
    industrial_zone: str | None
    purdue_level: int | None
    lifecycle_state: str = "active"
    silent_since: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: uuid.UUID
    site_id: uuid.UUID
    source_alert_id: str
    severity: str | None
    status: str | None
    category: str | None
    cve_id: str | None
    title: str | None
    occurred_at: datetime | None
    asset_id: uuid.UUID | None = None
    closed_reason: str | None = None
    closed_at: datetime | None = None


class RemediationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    remediation_id: uuid.UUID
    site_id: uuid.UUID
    finding_id: uuid.UUID | None
    source_remediation_id: str
    title: str | None
    status: str | None
    owner: str | None
    planned_date: Any
    current_plan_version: int
    plan_history: list


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    incident_id: uuid.UUID
    site_id: uuid.UUID
    source_incident_id: str
    incident_source: str | None
    ecc_incident_id: str | None
    tribot_incident_id: str | None
    title: str | None
    severity: str | None
    priority: str | None
    status: str | None


class CorrelationGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correlation_group_id: uuid.UUID
    correlation_key: str
    title: str | None
    member_type: str
    member_ids: list
    site_ids: list = []          # sites the member alerts come from (filled by the route)


class TopologyLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    link_id: uuid.UUID
    site_id: uuid.UUID
    source_link_id: str
    source_asset_id: str
    target_asset_id: str
    protocol: str | None
    ports: list
    first_seen: datetime | None
    last_seen: datetime | None


class SiteHealthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: uuid.UUID
    health: dict
    received_at: datetime
    clock_skew_seconds: float | None


class TombstoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    site_id: uuid.UUID
    source_asset_id: str
    asset_name: str | None
    reason: str | None
    decommissioned_by: str | None
    decommissioned_at: datetime
    origin: str
    restored_at: datetime | None


class ConfirmDecommissionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
