import uuid

from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.correlation_group import CorrelationGroup
from app.models.fleet_asset import FleetAsset
from app.models.fleet_lifecycle import FleetAssetTombstone, FleetTopologyLink, SiteHealth
from app.models.incident import Incident
from app.models.remediation import Remediation
from app.services.fleet_scope import resolve_site_id_filter


class FleetService:
    def __init__(self, db: Session, restrict_to: set | None = None):
        """restrict_to: the site ids the caller may see (access_scope.
        visible_site_ids), applied on top of any requested filter; None = all."""
        self.db = db
        self.restrict_to = restrict_to

    def _scoped(self, model, site_id, site_ids, business_unit_id, business_unit_ids):
        query = self.db.query(model)
        site_id_filter = resolve_site_id_filter(
            self.db, site_id=site_id, site_ids=site_ids, business_unit_id=business_unit_id, business_unit_ids=business_unit_ids
        )
        if site_id_filter is not None:
            query = query.filter(model.site_id.in_(site_id_filter))
        if self.restrict_to is not None:
            query = query.filter(model.site_id.in_(self.restrict_to))
        return query

    @staticmethod
    def _page(query, order_by, limit: int | None, offset: int) -> tuple[list, int]:
        """(rows, total). `total` counts the whole filtered set, so a client
        can page through 100k+ rows across hundreds of sites."""
        total = query.order_by(None).count()
        query = query.order_by(*order_by).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return query.all(), total

    def list_assets(self, *, site_id=None, site_ids=None, business_unit_id=None, business_unit_ids=None,
                    limit: int | None = None, offset: int = 0,
                    lifecycle_state: str | None = None) -> tuple[list[FleetAsset], int]:
        query = self._scoped(FleetAsset, site_id, site_ids, business_unit_id, business_unit_ids)
        if lifecycle_state:
            query = query.filter(FleetAsset.lifecycle_state == lifecycle_state)
        return self._page(query, (FleetAsset.last_seen_at.desc().nullslast(), FleetAsset.asset_id), limit, offset)

    def list_alerts(self, *, site_id=None, site_ids=None, business_unit_id=None, business_unit_ids=None,
                    limit: int | None = None, offset: int = 0) -> tuple[list[Alert], int]:
        query = self._scoped(Alert, site_id, site_ids, business_unit_id, business_unit_ids)
        return self._page(query, (Alert.occurred_at.desc().nullslast(), Alert.alert_id), limit, offset)

    def list_remediations(self, *, site_id=None, site_ids=None, business_unit_id=None, business_unit_ids=None,
                          limit: int | None = None, offset: int = 0) -> tuple[list[Remediation], int]:
        query = self._scoped(Remediation, site_id, site_ids, business_unit_id, business_unit_ids)
        return self._page(query, (Remediation.updated_at.desc(), Remediation.remediation_id), limit, offset)

    def list_incidents(self, *, site_id=None, site_ids=None, business_unit_id=None, business_unit_ids=None,
                       limit: int | None = None, offset: int = 0) -> tuple[list[Incident], int]:
        query = self._scoped(Incident, site_id, site_ids, business_unit_id, business_unit_ids)
        return self._page(query, (Incident.updated_at.desc(), Incident.incident_id), limit, offset)

    def list_correlation_groups(self) -> list[CorrelationGroup]:
        # Tenant-wide by nature (FR-3.6 groups across sites within a tenant);
        # in SINGLE_TENANT mode that's simply every row.
        return self.db.query(CorrelationGroup).order_by(CorrelationGroup.updated_at.desc()).all()

    def list_topology_links(self, *, site_id=None, site_ids=None, business_unit_id=None, business_unit_ids=None,
                            limit: int | None = None, offset: int = 0) -> tuple[list[FleetTopologyLink], int]:
        query = self._scoped(FleetTopologyLink, site_id, site_ids, business_unit_id, business_unit_ids)
        return self._page(query, (FleetTopologyLink.site_id, FleetTopologyLink.source_link_id), limit, offset)

    def list_site_health(self, *, site_id=None, site_ids=None, business_unit_id=None,
                         business_unit_ids=None) -> list[SiteHealth]:
        return self._scoped(SiteHealth, site_id, site_ids, business_unit_id, business_unit_ids).order_by(
            SiteHealth.site_id).all()

    def list_tombstones(self, *, site_id=None, site_ids=None, business_unit_id=None, business_unit_ids=None,
                        limit: int | None = None, offset: int = 0) -> tuple[list[FleetAssetTombstone], int]:
        query = self._scoped(FleetAssetTombstone, site_id, site_ids, business_unit_id, business_unit_ids)
        return self._page(query, (FleetAssetTombstone.decommissioned_at.desc(),
                                  FleetAssetTombstone.tombstone_id), limit, offset)
