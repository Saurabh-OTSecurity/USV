"""Shared query-parameter convention for FR-3.1's site-wise / BU-compiled /
tenant-compiled view split (ECC_USV_PLATFORM_SPEC.md Section 4.3, T-3):
`?siteId=` for one site, `?businessUnitId=` for a Business Unit's sites, or
neither for the fully compiled (tenant-wide) view -- "not a one-off
dashboard feature," applied identically across every fleet endpoint rather
than each route inventing its own filtering.
"""
import uuid

from sqlalchemy.orm import Session

from app.models.site import Site


def _parse_uuid_csv(value: str | None) -> list[uuid.UUID]:
    if not value:
        return []
    return [uuid.UUID(part.strip()) for part in value.split(",") if part.strip()]


def resolve_site_id_filter(
    db: Session,
    *,
    site_id: uuid.UUID | None = None,
    site_ids: str | None = None,
    business_unit_id: uuid.UUID | None = None,
    business_unit_ids: str | None = None,
) -> list[uuid.UUID] | None:
    """Returns None for "no filter, full compiled view", or a (possibly
    empty) list of site_ids to restrict to. An empty list is a legitimate
    result (e.g. a Business Unit with no sites yet) and must be treated as
    "match nothing", not "match everything"."""
    explicit_site_ids: list[uuid.UUID] = []
    if site_id is not None:
        explicit_site_ids.append(site_id)
    explicit_site_ids.extend(_parse_uuid_csv(site_ids))

    bu_ids: list[uuid.UUID] = []
    if business_unit_id is not None:
        bu_ids.append(business_unit_id)
    bu_ids.extend(_parse_uuid_csv(business_unit_ids))

    if not explicit_site_ids and not bu_ids:
        return None

    resolved = set(explicit_site_ids)
    if bu_ids:
        rows = db.query(Site.site_id).filter(Site.business_unit_id.in_(bu_ids)).all()
        resolved.update(row[0] for row in rows)

    return list(resolved)
