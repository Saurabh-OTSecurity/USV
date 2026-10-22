"""Tribot's External Data API, served per pushed site from what that site's
Tribot pushed (fleet_asset, alert, fleet_topology_link, fleet_object).

Same path suffixes, query parameters and response shapes as /api/v1/tribot/*
(app/api/routes/tribot.py, which proxies ONE live Tribot), so USV's existing
OT Asset > Tribot pages render any onboarded site unchanged -- the "click a
site, get the Tribot view" of the USV O&M Manual section 4, without USV
having to reach into sites that only allow outbound traffic.

Per-site volumes are small (hundreds to a few thousand records), so filtering,
sorting and paging run in Python over the site's rows. Cursors are offsets.
"""
import hashlib
import uuid
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user, get_db
from app.models.alert import Alert
from app.models.fleet_asset import FleetAsset
from app.models.fleet_lifecycle import FleetObject, FleetTopologyLink
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.services.access_scope import can_view_site

router = APIRouter(prefix="/api/v1/fleet/sites/{site_id}/tribot", tags=["site-tribot"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
CASE_STATUSES = ("New", "InProgress", "Contained", "ClosurePending", "Closed")
PURDUE_DEFAULT = [("L1", "L1 - Basic Control & Physical Process"), ("L2", "L2 - Area Supervisory Control"),
                  ("L3", "L3 - Site Operations"), ("L3.5", "L3.5 - Industrial DMZ"),
                  ("L4", "L4 - External / Enterprise / Internet")]

ASSET_SORT = {"id", "riskScore", "lastSeen", "firstSeen", "hostname", "ip", "vendor", "manufacturer", "modelNumber",
              "deviceType", "primaryDomain", "functionalCategory", "productFamily", "confidenceScore", "industrialZone"}
ASSET_FILTERABLE = ["ip", "mac", "macVendor", "hostname", "vendor", "manufacturer", "deviceType", "role",
                    "controllerType", "primaryDomain", "functionalCategory", "productFamily", "productSeries",
                    "modelNumber", "firmwareVersion", "hardwareRevision", "serialNumber", "operatingSystem",
                    "osVersion", "industrialZone", "safetyImpact", "internetExposure", "operationalCriticality",
                    "subnet", "sourceInterface", "riskLevel", "healthStatus", "normalizationStatus",
                    "collectionMethod", "protocols"]
ASSET_SEARCH = ("ip", "mac", "hostname", "vendor", "manufacturer", "modelNumber", "operatingSystem", "primaryDomain",
                "functionalCategory")
ALERT_SORT = {"id": "alertId", "createdAt": "createdAt", "severity": "severity", "status": "status",
              "category": "category", "risk": "risk"}
ALERT_SEARCH = ("title", "description", "assetIp", "assetName", "category", "ruleId")
VULN_SORT = {"id": "vulnerabilityId", "cvssScore": "cvssScore", "severity": "severity", "cveId": "cveId",
             "assetIp": "assetIp"}
SOFTWARE_SORT = {"id": "softwareId", "displayName": "displayName", "displayVersion": "displayVersion",
                 "publisher": "publisher", "installDate": "installDate", "collectedAt": "collectedAt"}
PATCH_SORT = {"id": "patchId", "hotfixId": "hotfixId", "description": "description", "installedOn": "installedOn",
              "collectedAt": "collectedAt"}
CASE_SORT = {"id": "caseId", "caseNumber": "caseNumber", "createdAt": "createdAt", "updatedAt": "updatedAt"}


def _request_id() -> str:
    return f"req_{uuid.uuid4()}"


def _bad(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"error": {"code": "invalid_query_parameter", "message": message}})


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"error": {"code": "not_found", "message": f"{what} not found"}})


def _site(db: Session, user: UsvUser, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None or not can_view_site(db, user, site_id):
        raise _not_found("Site")
    return site


def _text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return "" if value is None else str(value)


def _match(item: dict, field: str, wanted: Optional[str]) -> bool:
    return wanted is None or _text(item.get(field)).lower() == wanted.lower()


def _search(item: dict, fields, term: Optional[str]) -> bool:
    if not term:
        return True
    term = term.lower()
    return any(term in _text(item.get(f)).lower() for f in fields)


def _sorted(items: list, sort: Optional[str], allow: dict, default_key: str) -> list:
    if not sort:
        key, desc = default_key, False
    else:
        desc = sort.startswith("-")
        name = sort[1:] if desc else sort
        if name not in allow:
            raise _bad(f"'sort' must be one of: {', '.join(allow)} (optionally prefixed with '-')")
        key = allow[name]

    def k(item):
        v = item.get(key)
        return (v is None, v if isinstance(v, (int, float)) else _text(v).lower())
    return sorted(items, key=k, reverse=desc) if sort else items


def _page(items: list, pageSize: Optional[int], cursor: Optional[str]) -> dict:
    size = min(max(pageSize or DEFAULT_PAGE_SIZE, 1), MAX_PAGE_SIZE)
    try:
        start = int(cursor) if cursor else 0
    except ValueError:
        raise _bad("invalid 'cursor'")
    page = items[start:start + size]
    nxt = start + size if start + size < len(items) else None
    return {"data": page, "pagination": {"nextCursor": str(nxt) if nxt is not None else None, "pageSize": size,
                                         "totalCount": len(items)}, "requestId": _request_id()}


def _item(data) -> dict:
    return {"data": data, "requestId": _request_id()}


# ── loaders ──

def _assets(db: Session, site_id) -> list[dict]:
    out = []
    for a in db.execute(select(FleetAsset).where(FleetAsset.site_id == site_id)).scalars():
        raw = dict(a.raw or {})
        raw.setdefault("assetId", a.source_asset_id)
        raw.setdefault("hostname", a.name)
        raw.setdefault("protocols", [])
        raw["lifecycleState"] = a.lifecycle_state
        out.append(raw)
    return out


def _objects(db: Session, site_id, object_type: str, asset_id: Optional[str] = None) -> list[dict]:
    q = select(FleetObject).where(FleetObject.site_id == site_id, FleetObject.object_type == object_type)
    if asset_id is not None:
        q = q.where(FleetObject.asset_source_id == asset_id)
    return [dict(o.raw) for o in db.execute(q).scalars()]


def _alerts(db: Session, site_id) -> list[dict]:
    out = []
    for a in db.execute(select(Alert).where(Alert.site_id == site_id)).scalars():
        raw = dict(a.raw or {})
        raw.setdefault("alertId", a.source_alert_id)
        for key, value in (("severity", a.severity), ("status", a.status), ("category", a.category),
                           ("title", a.title), ("description", a.description)):
            if raw.get(key) is None:
                raw[key] = value
        if a.closed_reason:
            raw["status"] = a.status
        out.append(raw)
    return out


def _config(db: Session, site_id) -> dict:
    rows = _objects(db, site_id, "site_config")
    return rows[0] if rows else {}


# ── assets ──

@router.get("/assets")
def list_assets(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                sort: Optional[str] = None, deviceType: Optional[str] = None, riskLevel: Optional[str] = None,
                industrialZone: Optional[str] = None, primaryDomain: Optional[str] = None,
                search: Optional[str] = None, filterBy: Optional[str] = None, filterValue: Optional[str] = None,
                db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    if (filterBy is None) != (filterValue is None):
        raise _bad("'filterBy' and 'filterValue' go together")
    if filterBy is not None and filterBy not in ASSET_FILTERABLE:
        raise _bad(f"'filterBy' must be one of: {', '.join(ASSET_FILTERABLE)}")
    items = [a for a in _assets(db, site_id)
             if _match(a, "deviceType", deviceType) and _match(a, "riskLevel", riskLevel)
             and _match(a, "industrialZone", industrialZone) and _match(a, "primaryDomain", primaryDomain)
             and _search(a, ASSET_SEARCH, search)
             and (filterBy is None or filterValue.lower() in _text(a.get(filterBy)).lower())]
    return _page(_sorted(items, sort, {k: k for k in ASSET_SORT} | {"id": "id"}, "id"), pageSize, cursor)


@router.get("/assets/facets")
def asset_facets(site_id: uuid.UUID, field: Optional[str] = None, limit: Optional[int] = None,
                 db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    if field not in ASSET_FILTERABLE:
        raise _bad(f"'field' must be one of: {', '.join(ASSET_FILTERABLE)}")
    counts: Counter = Counter()
    for a in _assets(db, site_id):
        value = a.get(field)
        values = value if isinstance(value, list) else [value]
        for v in values or [None]:
            counts[_text(v).strip() or "Unknown"] += 1
    ordered = counts.most_common(min(limit or 50, 500))
    return _item({"field": field, "values": [{"value": v, "count": n} for v, n in ordered]})


@router.get("/assets/filterable-fields")
def asset_filterable_fields(site_id: uuid.UUID, db: Session = Depends(get_db),
                            current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    return _item(ASSET_FILTERABLE)


@router.get("/assets/summary")
def asset_summary(site_id: uuid.UUID, db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    assets = _assets(db, site_id)

    def group(field):
        return dict(Counter(_text(a.get(field)) or "Unknown" for a in assets))
    return _item({
        "total": len(assets), "byDomain": group("primaryDomain"), "byRiskLevel": group("riskLevel"),
        "byDeviceType": group("deviceType"),
        "riskCriticalOrHigh": sum(1 for a in assets if (a.get("riskScore") or 0) >= 50),
        "withCves": sum(1 for a in assets if (a.get("cveCount") or 0) > 0),
        "withEol": sum(1 for a in assets if (a.get("eolCount") or 0) > 0),
    })


@router.get("/assets/{asset_id}")
def get_asset(site_id: uuid.UUID, asset_id: str, db: Session = Depends(get_db),
              current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    found = next((a for a in _assets(db, site_id) if str(a.get("assetId")) == asset_id), None)
    if found is None:
        raise _not_found("Asset")
    return _item(found)


def _asset_children(db, site_id, asset_id, object_type, sort, allow, search_fields, search, pageSize, cursor):
    items = [o for o in _objects(db, site_id, object_type, asset_id) if _search(o, search_fields, search)]
    return _page(_sorted(items, sort, allow, "id"), pageSize, cursor)


@router.get("/assets/{asset_id}/software")
def asset_software(site_id: uuid.UUID, asset_id: str, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                   sort: Optional[str] = None, search: Optional[str] = None,
                   db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    return _asset_children(db, site_id, asset_id, "software", sort, SOFTWARE_SORT,
                           ("displayName", "publisher", "displayVersion"), search, pageSize, cursor)


@router.get("/assets/{asset_id}/patches")
def asset_patches(site_id: uuid.UUID, asset_id: str, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                  sort: Optional[str] = None, search: Optional[str] = None,
                  db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    return _asset_children(db, site_id, asset_id, "patch", sort, PATCH_SORT, ("hotfixId", "description"),
                           search, pageSize, cursor)


# ── vulnerabilities ──

def _bool(value: Optional[str]) -> Optional[bool]:
    return None if value is None else value.lower() in ("1", "true", "yes")


@router.get("/vulnerabilities")
def list_vulnerabilities(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                         sort: Optional[str] = None, severity: Optional[str] = None, assetId: Optional[str] = None,
                         cveId: Optional[str] = None, hasExploit: Optional[str] = None, cisaKev: Optional[str] = None,
                         search: Optional[str] = None,
                         db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    exploit, kev = _bool(hasExploit), _bool(cisaKev)
    items = [v for v in _objects(db, site_id, "vulnerability")
             if _match(v, "severity", severity) and _match(v, "assetId", assetId) and _match(v, "cveId", cveId)
             and (exploit is None or bool(v.get("hasExploit")) == exploit)
             and (kev is None or bool(v.get("cisaKev")) == kev)
             and _search(v, ("cveId", "title", "assetIp"), search)]
    return _page(_sorted(items, sort, VULN_SORT, "id"), pageSize, cursor)


@router.get("/vulnerabilities/summary")
def vulnerability_summary(site_id: uuid.UUID, db: Session = Depends(get_db),
                          current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    vulns = _objects(db, site_id, "vulnerability")
    by_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for v in vulns:
        key = _text(v.get("severity")).lower()
        if key in by_sev:
            by_sev[key] += 1
    return _item({"total": len(vulns), "bySeverity": by_sev,
                  "withExploits": sum(1 for v in vulns if v.get("hasExploit")),
                  "cisaKev": sum(1 for v in vulns if v.get("cisaKev"))})


@router.get("/vulnerabilities/{vulnerability_id}")
def get_vulnerability(site_id: uuid.UUID, vulnerability_id: str, db: Session = Depends(get_db),
                      current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    found = next((v for v in _objects(db, site_id, "vulnerability")
                  if str(v.get("vulnerabilityId")) == vulnerability_id), None)
    if found is None:
        raise _not_found("Vulnerability")
    return _item(found)


# ── alerts ──

@router.get("/alerts")
def list_alerts(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                sort: Optional[str] = None, severity: Optional[str] = None, status: Optional[str] = None,
                category: Optional[str] = None, assetId: Optional[str] = None, search: Optional[str] = None,
                db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    items = [a for a in _alerts(db, site_id)
             if _match(a, "severity", severity) and _match(a, "status", status) and _match(a, "category", category)
             and _match(a, "assetId", assetId) and _search(a, ALERT_SEARCH, search)]
    return _page(_sorted(items, sort or "-createdAt", ALERT_SORT, "id"), pageSize, cursor)


@router.get("/alerts/summary")
def alert_summary(site_id: uuid.UUID, db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    alerts = _alerts(db, site_id)
    severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in alerts:
        key = _text(a.get("severity")).lower()
        if key in severity:
            severity[key] += 1
    severity["total"] = len(alerts)
    return _item({"severity": severity,
                  "categories": dict(Counter(_text(a.get("category")) or "Unknown" for a in alerts)),
                  "byStatus": dict(Counter(_text(a.get("status")) or "Unknown" for a in alerts))})


@router.get("/alerts/{alert_id}")
def get_alert(site_id: uuid.UUID, alert_id: str, db: Session = Depends(get_db),
              current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    found = next((a for a in _alerts(db, site_id) if str(a.get("alertId")) == alert_id), None)
    if found is None:
        raise _not_found("Alert")
    return _item(found)


# ── topology ──

def _zones(db: Session, site_id, assets: list[dict]) -> list[dict]:
    zones = _config(db, site_id).get("zones")
    if zones:
        return zones
    counts = Counter(a.get("industrialZone") for a in assets if a.get("industrialZone"))
    return [{"zoneId": n, "name": n, "purdueLevel": None, "color": None, "description": None, "sortOrder": None,
             "assetCount": c, "configured": False} for n, c in sorted(counts.items())]


def _node(asset: dict, zones_by_name: dict) -> dict:
    zone = zones_by_name.get(asset.get("industrialZone"))
    node = {
        "nodeId": asset.get("assetId"), "label": asset.get("hostname") or asset.get("ip"),
        "deviceType": asset.get("deviceType"), "zoneId": asset.get("industrialZone"),
        "ip": asset.get("ip"), "hostname": asset.get("hostname"), "mac": asset.get("mac"),
        "vendor": asset.get("vendor"), "manufacturer": asset.get("manufacturer"),
        "riskScore": asset.get("riskScore"), "riskLevel": asset.get("riskLevel"),
        "confidenceScore": asset.get("confidenceScore"), "protocols": asset.get("protocols") or [],
        "operationalCriticality": asset.get("operationalCriticality"), "safetyImpact": asset.get("safetyImpact"),
        "cveCount": asset.get("cveCount") or 0, "eolCount": asset.get("eolCount") or 0,
        "lifecycle": "End of Support" if (asset.get("eolCount") or 0) > 0 else "Supported",
        "lifecycleState": asset.get("lifecycleState"),
    }
    if zone:
        node["zone"] = {"name": zone.get("name"), "purdueLevel": zone.get("purdueLevel"),
                        "color": zone.get("color"), "description": zone.get("description")}
    return node


def _conversation_id(a: str, b: str) -> str:
    low, high = sorted([a or "", b or ""])
    return "conv_" + hashlib.sha256("|".join([low, high]).encode("utf-8")).hexdigest()[:32]


def _conversations(db: Session, site_id) -> list[dict]:
    """Every link between a pair of assets folded into one conversation, in
    both directions -- like Tribot's /topology/conversations."""
    pairs: dict = {}
    for link in db.execute(select(FleetTopologyLink).where(FleetTopologyLink.site_id == site_id)).scalars():
        raw = link.raw or {}
        cid = _conversation_id(link.source_asset_id, link.target_asset_id)
        conv = pairs.get(cid)
        if conv is None:
            conv = pairs[cid] = {
                "conversationId": cid, "sourceNodeId": link.source_asset_id, "targetNodeId": link.target_asset_id,
                "sourceIp": None, "targetIp": None, "protocols": [], "packetCount": 0, "byteCount": 0,
                "flowCount": 0, "bidirectional": False, "firstSeen": None, "lastSeen": None,
                "sourceZoneId": raw.get("sourceZoneId"), "targetZoneId": raw.get("targetZoneId"),
                "_directions": set(),
            }
        conv["_directions"].add((link.source_asset_id, link.target_asset_id))
        if link.protocol and link.protocol not in conv["protocols"]:
            conv["protocols"] = sorted(conv["protocols"] + [link.protocol])
        conv["packetCount"] += raw.get("packetCount") or 0
        conv["byteCount"] += raw.get("byteCount") or 0
        conv["flowCount"] += raw.get("flowCount") or 1
        for key, pick in (("firstSeen", min), ("lastSeen", max)):
            if raw.get(key):
                conv[key] = raw[key] if conv[key] is None else pick(conv[key], raw[key])
    for conv in pairs.values():
        conv["bidirectional"] = len(conv.pop("_directions")) > 1
    return list(pairs.values())


def _with_ips(convs: list[dict], assets: list[dict]) -> list[dict]:
    ip = {a.get("assetId"): a.get("ip") for a in assets}
    for c in convs:
        c["sourceIp"], c["targetIp"] = ip.get(c["sourceNodeId"]), ip.get(c["targetNodeId"])
    return convs


@router.get("/topology")
def get_topology(site_id: uuid.UUID, pageSize: Optional[int] = None, db: Session = Depends(get_db),
                 current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    assets = _assets(db, site_id)
    zones = {z["name"]: z for z in _zones(db, site_id, assets)}
    size = min(max(pageSize or MAX_PAGE_SIZE, 1), 5000)
    nodes = [_node(a, zones) for a in assets][:size]
    present = {n["nodeId"] for n in nodes}
    links = [c for c in _with_ips(_conversations(db, site_id), assets)
             if c["sourceNodeId"] in present and c["targetNodeId"] in present]
    return _item({"nodes": nodes, "links": links})


@router.get("/topology/conversations")
def topology_conversations(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                           db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    return _page(_with_ips(_conversations(db, site_id), _assets(db, site_id)), pageSize, cursor)


@router.get("/topology/nodes")
def topology_nodes(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                   deviceType: Optional[str] = None, zoneId: Optional[str] = None,
                   db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    assets = _assets(db, site_id)
    zones = {z["name"]: z for z in _zones(db, site_id, assets)}
    nodes = [_node(a, zones) for a in assets
             if _match(a, "deviceType", deviceType) and _match(a, "industrialZone", zoneId)]
    return _page(nodes, pageSize, cursor)


@router.get("/topology/links")
def topology_links(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                   protocol: Optional[str] = None, sourceNodeId: Optional[str] = None,
                   targetNodeId: Optional[str] = None,
                   db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    links = [dict(l.raw or {}) for l in db.execute(
        select(FleetTopologyLink).where(FleetTopologyLink.site_id == site_id)).scalars()]
    links = [l for l in links if _match(l, "protocol", protocol) and _match(l, "sourceNodeId", sourceNodeId)
             and _match(l, "targetNodeId", targetNodeId)]
    return _page(links, pageSize, cursor)


@router.get("/topology/purdue-levels")
def purdue_levels(site_id: uuid.UUID, db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    levels = _config(db, site_id).get("purdueLevels") or [
        {"levelKey": k, "numeric": i, "displayLabel": label} for i, (k, label) in enumerate(PURDUE_DEFAULT)]
    return {"data": levels, "requestId": _request_id()}


@router.get("/topology/zones")
def topology_zones(site_id: uuid.UUID, db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    return {"data": _zones(db, site_id, _assets(db, site_id)), "requestId": _request_id()}


# ── IR cases (read-only status mirror) ──

def _cases(db: Session, site_id) -> list[dict]:
    return _objects(db, site_id, "ir_case")


@router.get("/ir-cases/board")
def ir_case_board(site_id: uuid.UUID, db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    cases = _cases(db, site_id)
    by_status = Counter(c.get("status") for c in cases)
    open_cases = [c for c in cases if c.get("status") != "Closed"]
    by_tier = Counter(c.get("pendingTier") for c in open_cases if c.get("pendingTier"))
    cards: dict = {s: [] for s in CASE_STATUSES}
    for c in sorted(open_cases, key=lambda c: _text(c.get("createdAt")), reverse=True)[:200]:
        cards.setdefault(c.get("status") or "New", []).append(c)
    return _item({"columns": [{"status": s, "count": by_status.get(s, 0)} for s in CASE_STATUSES],
                  "pendingOn": [{"tier": t, "count": n} for t, n in sorted(by_tier.items())],
                  "totalOpen": len(open_cases), "cards": cards})


@router.get("/ir-cases")
def list_ir_cases(site_id: uuid.UUID, pageSize: Optional[int] = None, cursor: Optional[str] = None,
                  sort: Optional[str] = None, status: Optional[str] = None, severity: Optional[str] = None,
                  pendingTier: Optional[str] = None, assetId: Optional[str] = None,
                  db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    items = [c for c in _cases(db, site_id)
             if _match(c, "status", status) and _match(c, "severity", severity)
             and _match(c, "pendingTier", pendingTier) and _match(c, "assetId", assetId)]
    return _page(_sorted(items, sort, CASE_SORT, "id"), pageSize, cursor)


@router.get("/ir-cases/{case_id}")
def get_ir_case(site_id: uuid.UUID, case_id: str, db: Session = Depends(get_db),
                current_user: UsvUser = Depends(get_current_user)):
    _site(db, current_user, site_id)
    found = next((c for c in _cases(db, site_id) if str(c.get("caseId")) == case_id), None)
    if found is None:
        raise _not_found("Case")
    return _item(found)
