from app.services.tribot_client import TribotClient


class TribotService:
    """Orchestrates calls to Tribot's External Data API for the
    OT Asset -> Tribot screens. No local persistence: every call is a live,
    read-only proxy to Tribot (see app/services/tribot_client.py) -- there is
    no USV-side caching or reshaping of Tribot's response bodies.
    """

    def __init__(self, client: TribotClient | None = None):
        self.client = client or TribotClient()

    def list_assets(self, params: dict) -> dict:
        return self.client.list_assets(params)

    def get_asset(self, asset_id: str) -> dict:
        return self.client.get_asset(asset_id)

    def list_vulnerabilities(self, params: dict) -> dict:
        return self.client.list_vulnerabilities(params)

    def get_vulnerability(self, vulnerability_id: str) -> dict:
        return self.client.get_vulnerability(vulnerability_id)

    def list_alerts(self, params: dict) -> dict:
        return self.client.list_alerts(params)

    def get_alert(self, alert_id: str) -> dict:
        return self.client.get_alert(alert_id)

    def list_asset_software(self, asset_id: str, params: dict) -> dict:
        return self.client.list_asset_software(asset_id, params)

    def list_asset_patches(self, asset_id: str, params: dict) -> dict:
        return self.client.list_asset_patches(asset_id, params)

    def get_asset_facets(self, params: dict) -> dict:
        return self.client.get_asset_facets(params)

    def list_asset_filterable_fields(self) -> dict:
        return self.client.list_asset_filterable_fields()

    def get_asset_summary(self) -> dict:
        return self.client.get_asset_summary()

    def get_alert_summary(self) -> dict:
        return self.client.get_alert_summary()

    def get_vulnerability_summary(self) -> dict:
        return self.client.get_vulnerability_summary()

    def get_ir_case_board(self) -> dict:
        return self.client.get_ir_case_board()

    def list_ir_cases(self, params: dict) -> dict:
        return self.client.list_ir_cases(params)

    def get_ir_case(self, case_id: str) -> dict:
        return self.client.get_ir_case(case_id)

    def get_topology(self, params: dict) -> dict:
        return self.client.get_topology(params)

    def list_topology_conversations(self, params: dict) -> dict:
        return self.client.list_topology_conversations(params)

    def list_purdue_levels(self) -> dict:
        return self.client.list_purdue_levels()

    def list_topology_zones(self) -> dict:
        return self.client.list_topology_zones()

    def list_topology_nodes(self, params: dict) -> dict:
        return self.client.list_topology_nodes(params)

    def list_topology_links(self, params: dict) -> dict:
        return self.client.list_topology_links(params)
