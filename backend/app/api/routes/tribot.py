"""Proxy for Tribot's External Data API (OT Asset -> Tribot screens).

Every endpoint here mirrors one of Tribot's actual read-only /api/v1/*
endpoints (see Triot_Detection-Engine_Api/Specifications/
TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md, Section 3.2) -- same path
suffix, same query parameters, same response shape. USV never calls the
database directly for this data; app.services.tribot_service proxies live to
Tribot and this route just authenticates the USV caller and translates
app.services.tribot_client.TribotClientError into USV's error contract.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.rbac import get_current_user
from app.models.usv_user import UsvUser
from app.services.tribot_client import TribotClientError
from app.services.tribot_service import TribotService

router = APIRouter(prefix="/api/v1/tribot", tags=["tribot"])


def _service() -> TribotService:
    return TribotService()


def _run(fn):
    try:
        return fn()
    except TribotClientError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )


# ── Assets ──

@router.get("/assets")
def list_assets(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    deviceType: Optional[str] = None,
    riskLevel: Optional[str] = None,
    industrialZone: Optional[str] = None,
    primaryDomain: Optional[str] = None,
    search: Optional[str] = None,
    filterBy: Optional[str] = None,
    filterValue: Optional[str] = None,
    updatedAfter: Optional[str] = None,
    updatedBefore: Optional[str] = None,
):
    params = {
        "pageSize": pageSize, "cursor": cursor, "sort": sort, "deviceType": deviceType,
        "riskLevel": riskLevel, "industrialZone": industrialZone, "primaryDomain": primaryDomain,
        "search": search, "filterBy": filterBy, "filterValue": filterValue,
        "updatedAfter": updatedAfter, "updatedBefore": updatedBefore,
    }
    return _run(lambda: _service().list_assets(params))


@router.get("/assets/facets")
def get_asset_facets(
    current_user: UsvUser = Depends(get_current_user),
    field: Optional[str] = None,
    limit: Optional[int] = None,
):
    """Distinct values for one filterable column (parity gap A-08). Declared
    before /assets/{asset_id} so the literal path wins the route match."""
    return _run(lambda: _service().get_asset_facets({"field": field, "limit": limit}))


@router.get("/assets/filterable-fields")
def list_asset_filterable_fields(current_user: UsvUser = Depends(get_current_user)):
    """The columns a filter picker may offer (parity gap A-08)."""
    return _run(lambda: _service().list_asset_filterable_fields())


@router.get("/assets/summary")
def get_asset_summary(current_user: UsvUser = Depends(get_current_user)):
    """Whole-session asset aggregates (parity gap A-07). Declared before
    /assets/{asset_id} so the literal path wins the route match."""
    return _run(lambda: _service().get_asset_summary())


@router.get("/assets/{asset_id}")
def get_asset(asset_id: str, current_user: UsvUser = Depends(get_current_user)):
    return _run(lambda: _service().get_asset(asset_id))


@router.get("/assets/{asset_id}/software")
def list_asset_software(
    asset_id: str,
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    search: Optional[str] = None,
):
    """Installed applications for one asset (parity gap A-15)."""
    params = {"pageSize": pageSize, "cursor": cursor, "sort": sort, "search": search}
    return _run(lambda: _service().list_asset_software(asset_id, params))


@router.get("/assets/{asset_id}/patches")
def list_asset_patches(
    asset_id: str,
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    search: Optional[str] = None,
):
    """Installed hotfixes for one asset (parity gap A-15)."""
    params = {"pageSize": pageSize, "cursor": cursor, "sort": sort, "search": search}
    return _run(lambda: _service().list_asset_patches(asset_id, params))


# ── Vulnerabilities ──

@router.get("/vulnerabilities")
def list_vulnerabilities(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    severity: Optional[str] = None,
    assetId: Optional[str] = None,
    cveId: Optional[str] = None,
    hasExploit: Optional[bool] = None,
    cisaKev: Optional[bool] = None,
    search: Optional[str] = None,
    updatedAfter: Optional[str] = None,
    updatedBefore: Optional[str] = None,
):
    params = {
        "pageSize": pageSize, "cursor": cursor, "sort": sort, "severity": severity,
        "assetId": assetId, "cveId": cveId, "hasExploit": hasExploit, "cisaKev": cisaKev,
        "search": search, "updatedAfter": updatedAfter, "updatedBefore": updatedBefore,
    }
    return _run(lambda: _service().list_vulnerabilities(params))


@router.get("/vulnerabilities/summary")
def get_vulnerability_summary(current_user: UsvUser = Depends(get_current_user)):
    """The five KPI-card counts over the whole session (parity gap V-01)."""
    return _run(lambda: _service().get_vulnerability_summary())


@router.get("/vulnerabilities/{vulnerability_id}")
def get_vulnerability(vulnerability_id: str, current_user: UsvUser = Depends(get_current_user)):
    return _run(lambda: _service().get_vulnerability(vulnerability_id))


# ── Alerts ──

@router.get("/alerts")
def list_alerts(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    assetId: Optional[str] = None,
    search: Optional[str] = None,
    updatedAfter: Optional[str] = None,
    updatedBefore: Optional[str] = None,
):
    params = {
        "pageSize": pageSize, "cursor": cursor, "sort": sort, "severity": severity,
        "status": status, "category": category, "assetId": assetId, "search": search,
        "updatedAfter": updatedAfter, "updatedBefore": updatedBefore,
    }
    return _run(lambda: _service().list_alerts(params))


@router.get("/alerts/summary")
def get_alert_summary(current_user: UsvUser = Depends(get_current_user)):
    """Severity and per-category counts over the whole session (gap AL-01)."""
    return _run(lambda: _service().get_alert_summary())


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str, current_user: UsvUser = Depends(get_current_user)):
    return _run(lambda: _service().get_alert(alert_id))


# ── Topology ──

@router.get("/topology")
def get_topology(current_user: UsvUser = Depends(get_current_user), pageSize: Optional[int] = None):
    return _run(lambda: _service().get_topology({"pageSize": pageSize}))


@router.get("/topology/nodes")
def list_topology_nodes(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    deviceType: Optional[str] = None,
    zoneId: Optional[str] = None,
    updatedAfter: Optional[str] = None,
    updatedBefore: Optional[str] = None,
):
    params = {
        "pageSize": pageSize, "cursor": cursor, "sort": sort, "deviceType": deviceType,
        "zoneId": zoneId, "updatedAfter": updatedAfter, "updatedBefore": updatedBefore,
    }
    return _run(lambda: _service().list_topology_nodes(params))


@router.get("/topology/links")
def list_topology_links(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    protocol: Optional[str] = None,
    sourceNodeId: Optional[str] = None,
    targetNodeId: Optional[str] = None,
    updatedAfter: Optional[str] = None,
    updatedBefore: Optional[str] = None,
):
    params = {
        "pageSize": pageSize, "cursor": cursor, "sort": sort, "protocol": protocol,
        "sourceNodeId": sourceNodeId, "targetNodeId": targetNodeId,
        "updatedAfter": updatedAfter, "updatedBefore": updatedBefore,
    }
    return _run(lambda: _service().list_topology_links(params))


@router.get("/topology/conversations")
def list_topology_conversations(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
):
    """Aggregated asset-to-asset conversations (parity gap DT-17), replacing the
    arbitrary sample of raw Communication rows the topology screen used to
    draw."""
    params = {"pageSize": pageSize, "cursor": cursor}
    return _run(lambda: _service().list_topology_conversations(params))


@router.get("/topology/purdue-levels")
def list_purdue_levels(current_user: UsvUser = Depends(get_current_user)):
    """Ordered Purdue tiers with their admin-editable display labels (gap
    DT-02), so USV's topology never hardcodes tier names Tribot can rename."""
    return _run(lambda: _service().list_purdue_levels())


@router.get("/topology/zones")
def list_topology_zones(current_user: UsvUser = Depends(get_current_user)):
    """Zone roster with membership counts, including configured-but-empty and
    in-use-but-unconfigured zones (gap DT-15)."""
    return _run(lambda: _service().list_topology_zones())


# ── Incident Response case status (read-only mirror) ──
#
# Tribot exposes case *status* only: tasks, notes, observables, evidence and
# closure sign-off stay on its own internal /api/ir/ surface by design. USV can
# therefore render the Case Board and a read-only case summary, never work a
# case (parity gaps IR-01, IR-02, IR-03).

@router.get("/ir-cases/board")
def get_ir_case_board(current_user: UsvUser = Depends(get_current_user)):
    """The whole board in one call -- columns, per-tier pending counts, total
    open, and the open cases grouped by status. Declared before
    /ir-cases/{case_id} so the literal path wins the route match."""
    return _run(lambda: _service().get_ir_case_board())


@router.get("/ir-cases")
def list_ir_cases(
    current_user: UsvUser = Depends(get_current_user),
    pageSize: Optional[int] = None,
    cursor: Optional[str] = None,
    sort: Optional[str] = None,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    pendingTier: Optional[str] = None,
    assetId: Optional[str] = None,
    updatedAfter: Optional[str] = None,
    updatedBefore: Optional[str] = None,
):
    params = {
        "pageSize": pageSize, "cursor": cursor, "sort": sort, "status": status,
        "severity": severity, "pendingTier": pendingTier, "assetId": assetId,
        "updatedAfter": updatedAfter, "updatedBefore": updatedBefore,
    }
    return _run(lambda: _service().list_ir_cases(params))


@router.get("/ir-cases/{case_id}")
def get_ir_case(case_id: str, current_user: UsvUser = Depends(get_current_user)):
    return _run(lambda: _service().get_ir_case(case_id))
