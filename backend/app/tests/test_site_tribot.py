"""Per-site Tribot views (/api/v1/fleet/sites/{id}/tribot/*): a pushed site
served with the same shapes as Tribot's own External Data API, so USV's OT
Asset > Tribot pages render it unchanged."""
import uuid

from app.tests.test_asset_lifecycle import _env, _login, _push, _site, client  # noqa: F401  (fixture)


def _seed(client):
    site_id, auth, headers = _site(client)
    _push(client, auth,
          _env("asset", "A1", {"assetId": "A1", "hostname": "PLC-1", "ip": "10.0.0.1", "deviceType": "PLC",
                               "riskScore": 80, "riskLevel": "High", "industrialZone": "Control", "cveCount": 1}),
          _env("asset", "A2", {"assetId": "A2", "hostname": "HMI-1", "ip": "10.0.0.2", "deviceType": "HMI",
                               "riskScore": 10, "riskLevel": "Low", "industrialZone": "Control"}),
          _env("topology_link", "L1", {"linkId": "L1", "sourceNodeId": "A1", "targetNodeId": "A2",
                                       "protocol": "S7", "packetCount": 5, "flowCount": 2}),
          _env("topology_link", "L2", {"linkId": "L2", "sourceNodeId": "A2", "targetNodeId": "A1",
                                       "protocol": "Modbus", "packetCount": 3}),
          _env("alert", "AL1", {"alertId": "AL1", "assetId": "A1", "status": "Open", "severity": "High",
                                "title": "Program download", "createdAt": "2026-10-19T10:00:00Z"}),
          _env("vulnerability", "V1", {"vulnerabilityId": "V1", "assetId": "A1", "cveId": "CVE-2026-0001",
                                       "severity": "critical", "cvssScore": 9.8, "hasExploit": True}),
          _env("software", "S1", {"softwareId": "S1", "assetId": "A2", "displayName": "WinCC"}),
          _env("patch", "P1", {"patchId": "P1", "assetId": "A2", "hotfixId": "KB500"}),
          _env("ir_case", "C1", {"caseId": "C1", "caseNumber": "IR-1", "status": "InProgress", "title": "Case"}),
          _env("site_config", "site", {"configId": "site", "purdueLevels": [
              {"levelKey": "L1", "numeric": 0, "displayLabel": "Field"}],
              "zones": [{"zoneId": "Control", "name": "Control", "purdueLevel": 1, "color": "#f00",
                         "assetCount": 2, "configured": True}]}))
    return site_id, auth, headers


def test_site_views_mirror_tribot_shapes(client):
    site_id, auth, headers = _seed(client)
    base = f"/api/v1/fleet/sites/{site_id}/tribot"

    assets = client.get(f"{base}/assets?sort=-riskScore", headers=headers).json()
    assert [a["assetId"] for a in assets["data"]] == ["A1", "A2"] and assets["pagination"]["totalCount"] == 2
    assert client.get(f"{base}/assets?filterBy=deviceType&filterValue=hmi", headers=headers).json()["data"][0]["assetId"] == "A2"
    facets = client.get(f"{base}/assets/facets?field=deviceType", headers=headers).json()["data"]
    assert facets["field"] == "deviceType" and {v["value"] for v in facets["values"]} == {"PLC", "HMI"}
    assert client.get(f"{base}/assets/summary", headers=headers).json()["data"]["withCves"] == 1
    assert client.get(f"{base}/assets/A1", headers=headers).json()["data"]["hostname"] == "PLC-1"
    assert client.get(f"{base}/assets/A2/software", headers=headers).json()["data"][0]["displayName"] == "WinCC"
    assert client.get(f"{base}/assets/A2/patches", headers=headers).json()["data"][0]["hotfixId"] == "KB500"
    assert client.get(f"{base}/assets/nope", headers=headers).status_code == 404

    vulns = client.get(f"{base}/vulnerabilities?hasExploit=true", headers=headers).json()
    assert vulns["data"][0]["cveId"] == "CVE-2026-0001"
    assert client.get(f"{base}/vulnerabilities/summary", headers=headers).json()["data"]["bySeverity"]["critical"] == 1

    alerts = client.get(f"{base}/alerts", headers=headers).json()["data"]
    assert alerts[0]["alertId"] == "AL1" and alerts[0]["title"] == "Program download"
    assert client.get(f"{base}/alerts/summary", headers=headers).json()["data"]["severity"]["high"] == 1

    topo = client.get(f"{base}/topology", headers=headers).json()["data"]
    assert len(topo["nodes"]) == 2 and topo["nodes"][0]["zone"]["color"] == "#f00"
    [conv] = topo["links"]                                            # both directions fold into one
    assert conv["bidirectional"] and conv["protocols"] == ["Modbus", "S7"] and conv["packetCount"] == 8
    assert conv["flowCount"] == 3 and conv["conversationId"].startswith("conv_")
    assert client.get(f"{base}/topology/purdue-levels", headers=headers).json()["data"][0]["displayLabel"] == "Field"
    assert client.get(f"{base}/topology/zones", headers=headers).json()["data"][0]["configured"] is True

    board = client.get(f"{base}/ir-cases/board", headers=headers).json()["data"]
    assert board["totalOpen"] == 1 and board["cards"]["InProgress"][0]["caseNumber"] == "IR-1"
    assert client.get(f"{base}/ir-cases/C1", headers=headers).json()["data"]["status"] == "InProgress"


def test_inventory_prunes_objects_and_decommission_drops_asset_details(client):
    site_id, auth, headers = _seed(client)
    base = f"/api/v1/fleet/sites/{site_id}/tribot"
    _push(client, auth, _env("site_inventory", None, {"assetIds": ["A1", "A2"], "objectIds": {
        "vulnerability": [], "software": ["S1"], "patch": ["P1"], "ir_case": ["C1"], "topology_link": ["L1"]}},
        event_type="INVENTORY_COMPLETE"))
    assert client.get(f"{base}/vulnerabilities", headers=headers).json()["data"] == []
    assert client.get(f"{base}/topology", headers=headers).json()["data"]["links"][0]["bidirectional"] is False

    _push(client, auth, _env("asset", "A2", {"assetId": "A2", "reason": "replaced"}, event_type="ASSET_DECOMMISSIONED"))
    assert client.get(f"{base}/assets/A2/software", headers=headers).json()["data"] == []


def test_defaults_and_bad_queries(client):
    site_id, _, headers = _site(client)
    base = f"/api/v1/fleet/sites/{site_id}/tribot"
    levels = client.get(f"{base}/topology/purdue-levels", headers=headers).json()["data"]
    assert [l["levelKey"] for l in levels] == ["L1", "L2", "L3", "L3.5", "L4"]
    assert client.get(f"{base}/assets?sort=bogus", headers=headers).status_code == 400
    assert client.get(f"{base}/assets/facets?field=bogus", headers=headers).status_code == 400
    assert client.get(f"/api/v1/fleet/sites/{uuid.uuid4()}/tribot/assets", headers=headers).status_code == 404
