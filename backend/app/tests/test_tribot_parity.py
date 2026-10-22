"""Coverage for the USV half of the 2026-09-16 Tribot<->USV parity work.

The endpoints below existed on Tribot but had no USV proxy at all, so USV's
screens could not reach them (parity gaps A-07, A-15, AL-01, V-01, DT-02,
DT-15, IR-01, IR-02). Follows app/tests/test_tribot.py's conventions: a real
TestClient, settings patched to a configured Tribot, and httpx.get mocked so no
network call leaves the process.
"""
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _auth_header(client) -> dict:
    response = client.post(
        "/api/v1/auth/login", json={"username": "viewer.user", "password": "DevOnly!Viewer1"}
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _configured():
    return patch.multiple(settings, tribot_base_url="http://tribot.test", tribot_api_token="cred_1.secret")


def _mock_response(json_body, status_code=200):
    request = httpx.Request("GET", "http://tribot.test/")
    return httpx.Response(status_code=status_code, json=json_body, request=request)


def _called_url(mocked_get):
    return mocked_get.call_args[0][0]


def _called_params(mocked_get):
    return mocked_get.call_args.kwargs["params"]


# ── every new route requires authentication ──

NEW_ROUTES = [
    "/api/v1/tribot/assets/summary",
    "/api/v1/tribot/assets/a-1/software",
    "/api/v1/tribot/assets/a-1/patches",
    "/api/v1/tribot/alerts/summary",
    "/api/v1/tribot/vulnerabilities/summary",
    "/api/v1/tribot/topology/purdue-levels",
    "/api/v1/tribot/topology/zones",
    "/api/v1/tribot/ir-cases",
    "/api/v1/tribot/ir-cases/board",
    "/api/v1/tribot/ir-cases/7",
]


@pytest.mark.parametrize("path", NEW_ROUTES)
def test_new_routes_require_authentication(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", NEW_ROUTES)
def test_new_routes_report_unconfigured_tribot(client, path):
    headers = _auth_header(client)
    with patch.multiple(settings, tribot_base_url="", tribot_api_token=""):
        response = client.get(path, headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TRIBOT_NOT_CONFIGURED"


# ── A-15: software and patches per asset ──

def test_asset_software_proxies_verbatim_and_passes_search(client):
    headers = _auth_header(client)
    body = {
        "data": [{"softwareId": "1", "displayName": "Step7", "displayVersion": "5.6",
                   "publisher": "Siemens", "installDate": "2024-01-02", "collectedAt": None}],
        "pagination": {"nextCursor": None, "pageSize": 50, "totalCount": 1},
        "requestId": "req_1",
    }
    with _configured(), patch("httpx.get", return_value=_mock_response(body)) as mocked_get:
        response = client.get("/api/v1/tribot/assets/a-1/software?search=step&sort=publisher",
                               headers=headers)

    assert response.status_code == 200
    assert response.json() == body
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/assets/a-1/software"
    assert _called_params(mocked_get)["search"] == "step"
    assert _called_params(mocked_get)["sort"] == "publisher"


def test_asset_patches_proxies_verbatim(client):
    headers = _auth_header(client)
    body = {
        "data": [{"patchId": "1", "hotfixId": "KB5001", "description": "Security Update",
                   "installedOn": "2024-03-04", "collectedAt": None}],
        "pagination": {"nextCursor": None, "pageSize": 50, "totalCount": 1},
        "requestId": "req_2",
    }
    with _configured(), patch("httpx.get", return_value=_mock_response(body)) as mocked_get:
        response = client.get("/api/v1/tribot/assets/a-1/patches", headers=headers)

    assert response.status_code == 200
    assert response.json() == body
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/assets/a-1/patches"


def test_asset_software_forwards_tribot_404_for_unknown_asset(client):
    headers = _auth_header(client)
    error = {"error": {"code": "not_found", "message": "Asset not found"}}
    with _configured(), patch("httpx.get", return_value=_mock_response(error, status_code=404)):
        response = client.get("/api/v1/tribot/assets/nope/software", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# ── A-07 / AL-01 / V-01: summary aggregates ──

def test_asset_summary_is_not_captured_by_the_asset_detail_route(client):
    """/assets/summary must reach Tribot's own summary endpoint, not be parsed
    as an asset id by /assets/{asset_id}."""
    headers = _auth_header(client)
    body = {"data": {"total": 3, "byDomain": {"Industrial OT": 2}, "byRiskLevel": {},
                      "byDeviceType": {}, "riskCriticalOrHigh": 1, "withCves": 1, "withEol": 0},
            "requestId": "req_3"}
    with _configured(), patch("httpx.get", return_value=_mock_response(body)) as mocked_get:
        response = client.get("/api/v1/tribot/assets/summary", headers=headers)

    assert response.status_code == 200
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/assets/summary"
    assert response.json()["data"]["total"] == 3


def test_alert_and_vulnerability_summaries_reach_their_own_endpoints(client):
    headers = _auth_header(client)
    for path, upstream in (
        ("/api/v1/tribot/alerts/summary", "http://tribot.test/api/v1/alerts/summary"),
        ("/api/v1/tribot/vulnerabilities/summary", "http://tribot.test/api/v1/vulnerabilities/summary"),
    ):
        with _configured(), patch("httpx.get", return_value=_mock_response({"data": {}, "requestId": "r"})) as mocked_get:
            assert client.get(path, headers=headers).status_code == 200
            assert _called_url(mocked_get) == upstream


# ── P-02 / V-02: search and boolean filters are forwarded ──

def test_list_assets_forwards_search(client):
    headers = _auth_header(client)
    with _configured(), patch("httpx.get", return_value=_mock_response({"data": [], "pagination": {}, "requestId": "r"})) as mocked_get:
        client.get("/api/v1/tribot/assets?search=siemens", headers=headers)
    assert _called_params(mocked_get)["search"] == "siemens"


def test_list_vulnerabilities_forwards_exploit_and_kev_filters(client):
    headers = _auth_header(client)
    with _configured(), patch("httpx.get", return_value=_mock_response({"data": [], "pagination": {}, "requestId": "r"})) as mocked_get:
        client.get("/api/v1/tribot/vulnerabilities?hasExploit=true&cisaKev=false&search=cve",
                   headers=headers)
    params = _called_params(mocked_get)
    assert params["hasExploit"] is True
    # False must be forwarded, not dropped as falsy -- the client strips only None.
    assert params["cisaKev"] is False
    assert params["search"] == "cve"


def test_list_alerts_forwards_search(client):
    headers = _auth_header(client)
    with _configured(), patch("httpx.get", return_value=_mock_response({"data": [], "pagination": {}, "requestId": "r"})) as mocked_get:
        client.get("/api/v1/tribot/alerts?search=modbus", headers=headers)
    assert _called_params(mocked_get)["search"] == "modbus"


# ── DT-02 / DT-15: topology tier labels and zone roster ──

def test_purdue_levels_and_zones_proxy_verbatim(client):
    headers = _auth_header(client)
    tiers = {"data": [{"levelKey": "L1", "numeric": 0, "displayLabel": "Cell / Area"}], "requestId": "r"}
    with _configured(), patch("httpx.get", return_value=_mock_response(tiers)) as mocked_get:
        response = client.get("/api/v1/tribot/topology/purdue-levels", headers=headers)
    assert response.json() == tiers
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/topology/purdue-levels"

    zones = {"data": [{"zoneId": "Cell-A", "name": "Cell-A", "purdueLevel": 1, "assetCount": 2,
                        "configured": True}], "requestId": "r"}
    with _configured(), patch("httpx.get", return_value=_mock_response(zones)) as mocked_get:
        response = client.get("/api/v1/tribot/topology/zones", headers=headers)
    assert response.json() == zones
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/topology/zones"


# ── IR-01 / IR-02: the case board USV previously had no route for ──

def test_ir_case_board_proxies_verbatim(client):
    headers = _auth_header(client)
    body = {
        "data": {
            "columns": [{"status": "New", "count": 2}, {"status": "Closed", "count": 1}],
            "pendingOn": [{"tier": "L1", "count": 1}, {"tier": "L2", "count": 1},
                           {"tier": "L3", "count": 0}],
            "totalOpen": 2,
            "cards": {"New": [{"caseId": "1", "caseNumber": "IR-1", "title": "t",
                                "severity": "High", "status": "New", "pendingTier": "L1"}]},
        },
        "requestId": "req_board",
    }
    with _configured(), patch("httpx.get", return_value=_mock_response(body)) as mocked_get:
        response = client.get("/api/v1/tribot/ir-cases/board", headers=headers)

    assert response.status_code == 200
    assert response.json() == body
    # Must not be captured by /ir-cases/{case_id}.
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/ir-cases/board"


def test_ir_cases_list_forwards_filters(client):
    headers = _auth_header(client)
    with _configured(), patch("httpx.get", return_value=_mock_response({"data": [], "pagination": {}, "requestId": "r"})) as mocked_get:
        client.get("/api/v1/tribot/ir-cases?status=New&pendingTier=L2&severity=high", headers=headers)
    params = _called_params(mocked_get)
    assert params["status"] == "New"
    assert params["pendingTier"] == "L2"
    assert params["severity"] == "high"


def test_ir_case_detail_reaches_the_case_endpoint(client):
    headers = _auth_header(client)
    body = {"data": {"caseId": "7", "caseNumber": "IR-7", "status": "InProgress"}, "requestId": "r"}
    with _configured(), patch("httpx.get", return_value=_mock_response(body)) as mocked_get:
        response = client.get("/api/v1/tribot/ir-cases/7", headers=headers)
    assert response.status_code == 200
    assert _called_url(mocked_get) == "http://tribot.test/api/v1/ir-cases/7"


def test_ir_board_surfaces_tribot_upstream_failure(client):
    headers = _auth_header(client)
    with _configured(), patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        response = client.get("/api/v1/tribot/ir-cases/board", headers=headers)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "TRIBOT_UNAVAILABLE"
