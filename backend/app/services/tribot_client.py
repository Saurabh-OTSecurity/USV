"""Thin HTTP client for Tribot's External Data API (read-only, /api/v1/*),
per Triot_Detection-Engine_Api/Specifications/TRIBOT_EXTERNAL_DATA_API_ARCHITECTURE_v1.0.md.

Every method here maps 1:1 onto one of Tribot's actual GET endpoints
(Section 3.2 of that document) and returns Tribot's response body verbatim --
this client does not reshape, rename, or invent fields. Authentication is a
single bearer credential (Section 6), configured via TRIBOT_BASE_URL /
TRIBOT_API_TOKEN (see app/core/config.py).
"""
import httpx

from app.core.config import settings


class TribotClientError(Exception):
    """Raised for any failure calling Tribot -- not configured, unreachable,
    or Tribot itself returned an error. `status_code` is the HTTP status this
    app's own API should respond with; `body` is the JSON error body to
    forward (Tribot's own `{"error": {...}}` shape when available)."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class TribotClient:
    def __init__(self):
        self._base_url = settings.tribot_base_url.rstrip("/")
        self._token = settings.tribot_api_token
        self._timeout = settings.tribot_request_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._token)

    def _require_configured(self) -> None:
        if not self.is_configured:
            raise TribotClientError(
                503,
                "TRIBOT_NOT_CONFIGURED",
                "Tribot integration is not configured. Set TRIBOT_BASE_URL and TRIBOT_API_TOKEN.",
            )

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._require_configured()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            response = httpx.get(
                f"{self._base_url}{path}",
                params=clean_params,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            raise TribotClientError(504, "TRIBOT_TIMEOUT", "Timed out waiting for Tribot to respond.")
        except httpx.RequestError as exc:
            raise TribotClientError(502, "TRIBOT_UNAVAILABLE", f"Could not reach Tribot: {exc}")

        if response.status_code >= 400:
            message = f"Tribot returned HTTP {response.status_code}"
            code = "TRIBOT_UPSTREAM_ERROR"
            try:
                error = response.json().get("error")
                if isinstance(error, dict):
                    code = error.get("code", code)
                    message = error.get("message", message)
            except ValueError:
                pass
            raise TribotClientError(response.status_code, code, message)

        return response.json()

    # ── Assets ──
    def list_assets(self, params: dict) -> dict:
        return self._get("/api/v1/assets", params)

    def get_asset(self, asset_id: str) -> dict:
        return self._get(f"/api/v1/assets/{asset_id}")

    def get_asset_facets(self, params: dict) -> dict:
        """Distinct values + counts for one filterable column (parity gap
        A-08) -- the "then pick a value" half of the column filter."""
        return self._get("/api/v1/assets/facets", params)

    def list_asset_filterable_fields(self) -> dict:
        """Which columns may be filtered on. Served rather than hardcoded so a
        picker cannot offer a field Tribot would reject."""
        return self._get("/api/v1/assets/filterable-fields")

    # ── Vulnerabilities ──
    def list_vulnerabilities(self, params: dict) -> dict:
        return self._get("/api/v1/vulnerabilities", params)

    def get_vulnerability(self, vulnerability_id: str) -> dict:
        return self._get(f"/api/v1/vulnerabilities/{vulnerability_id}")

    # ── Alerts ──
    def list_alerts(self, params: dict) -> dict:
        return self._get("/api/v1/alerts", params)

    def get_alert(self, alert_id: str) -> dict:
        return self._get(f"/api/v1/alerts/{alert_id}")

    # ── Software & patches (per asset) ──
    # Tribot has published these since the TrustSweep work; USV simply never
    # consumed them (parity gap A-15).
    def list_asset_software(self, asset_id: str, params: dict) -> dict:
        return self._get(f"/api/v1/assets/{asset_id}/software", params)

    def list_asset_patches(self, asset_id: str, params: dict) -> dict:
        return self._get(f"/api/v1/assets/{asset_id}/patches", params)

    # ── Whole-dataset aggregates ──
    # Cursor pagination means USV holds one page, so the summary bars and KPI
    # cards on Tribot's screens can only come from a server-side aggregate
    # (parity gaps A-07, AL-01, V-01).
    def get_asset_summary(self) -> dict:
        return self._get("/api/v1/assets/summary")

    def get_alert_summary(self) -> dict:
        return self._get("/api/v1/alerts/summary")

    def get_vulnerability_summary(self) -> dict:
        return self._get("/api/v1/vulnerabilities/summary")

    # ── IR case status mirror (read-only) ──
    def get_ir_case_board(self) -> dict:
        return self._get("/api/v1/ir-cases/board")

    def list_ir_cases(self, params: dict) -> dict:
        return self._get("/api/v1/ir-cases", params)

    def get_ir_case(self, case_id: str) -> dict:
        return self._get(f"/api/v1/ir-cases/{case_id}")

    # ── Topology ──
    def get_topology(self, params: dict) -> dict:
        return self._get("/api/v1/topology", params)

    def list_topology_nodes(self, params: dict) -> dict:
        return self._get("/api/v1/topology/nodes", params)

    def list_topology_links(self, params: dict) -> dict:
        return self._get("/api/v1/topology/links", params)

    def list_topology_conversations(self, params: dict) -> dict:
        """Aggregated asset-to-asset conversations (parity gap DT-17). One row
        per endpoint pair with packets/bytes summed and the protocol set
        merged -- the pageable form of what /topology embeds."""
        return self._get("/api/v1/topology/conversations", params)

    def list_purdue_levels(self) -> dict:
        return self._get("/api/v1/topology/purdue-levels")

    def list_topology_zones(self) -> dict:
        return self._get("/api/v1/topology/zones")
