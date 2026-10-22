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
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _configured():
    return patch.multiple(settings, tribot_base_url="http://tribot.test", tribot_api_token="cred_1.secret")


def _mock_response(status_code=200, json_body=None):
    request = httpx.Request("GET", "http://tribot.test/api/v1/assets")
    return httpx.Response(status_code=status_code, json=json_body or {}, request=request)


def test_list_assets_requires_authentication(client):
    response = client.get("/api/v1/tribot/assets")
    assert response.status_code == 401


def test_list_assets_returns_503_when_tribot_not_configured(client):
    headers = _auth_header(client)
    with patch.multiple(settings, tribot_base_url="", tribot_api_token=""):
        response = client.get("/api/v1/tribot/assets", headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TRIBOT_NOT_CONFIGURED"


def test_list_assets_proxies_tribot_response_verbatim(client):
    headers = _auth_header(client)
    tribot_body = {
        "data": [{"assetId": "a-1", "ip": "10.0.0.5", "hostname": "plc-01", "riskScore": 22}],
        "pagination": {"nextCursor": None, "pageSize": 50},
        "requestId": "req_abc",
    }
    with _configured(), patch("httpx.get", return_value=_mock_response(200, tribot_body)) as mocked_get:
        response = client.get("/api/v1/tribot/assets?deviceType=PLC", headers=headers)

    assert response.status_code == 200
    assert response.json() == tribot_body
    called_url = mocked_get.call_args.args[0]
    called_params = mocked_get.call_args.kwargs["params"]
    called_headers = mocked_get.call_args.kwargs["headers"]
    assert called_url == "http://tribot.test/api/v1/assets"
    assert called_params == {"deviceType": "PLC"}
    assert called_headers == {"Authorization": "Bearer cred_1.secret"}


def test_get_asset_forwards_tribot_404(client):
    headers = _auth_header(client)
    error_body = {"error": {"code": "not_found", "message": "Asset not found", "requestId": "req_1"}}
    with _configured(), patch("httpx.get", return_value=_mock_response(404, error_body)):
        response = client.get("/api/v1/tribot/assets/does-not-exist", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Asset not found"}}


def test_list_alerts_returns_502_when_tribot_unreachable(client):
    headers = _auth_header(client)
    with _configured(), patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        response = client.get("/api/v1/tribot/alerts", headers=headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "TRIBOT_UNAVAILABLE"


def test_get_topology_proxies_nodes_and_links(client):
    headers = _auth_header(client)
    tribot_body = {
        "data": {
            "nodes": [{"nodeId": "a-1", "label": "plc-01", "deviceType": "PLC", "zoneId": "L2"}],
            "links": [{"linkId": "l1", "sourceNodeId": "a-1", "targetNodeId": "a-2", "protocol": "Modbus"}],
        },
        "requestId": "req_topo",
    }
    with _configured(), patch("httpx.get", return_value=_mock_response(200, tribot_body)):
        response = client.get("/api/v1/tribot/topology", headers=headers)

    assert response.status_code == 200
    assert response.json() == tribot_body
