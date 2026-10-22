"""Who may see and manage which sites (USV O&M Manual sections 2 and 11).

Levels, top down: platform -> customer -> business unit -> site. A person
sees their level and below:

- platform admin, customer admin, auditor: every site of the customer
  (in pool mode the customer IS the database, so "every site here");
- BU admin: the sites of their business unit (usv_user.business_unit_id);
- everyone else (site admin, analysts, operators, viewers): the sites they
  are assigned to (usv_user.site_id plus usv_user_site rows).

visible_site_ids() returns None for "no restriction". Lists intersect the
caller's own filters with it; single-object routes use can_view_site() /
can_manage_site().
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import (
    USV_AUDITOR, USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, USV_SITE_ADMIN,
)
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.models.usv_user_site import UsvUserSite

CUSTOMER_WIDE_ROLES = {USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_AUDITOR}
CUSTOMER_ADMIN_ROLES = {USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN}


def assigned_site_ids(db: Session, user: UsvUser) -> set[uuid.UUID]:
    ids = {row.site_id for row in db.execute(select(UsvUserSite).where(UsvUserSite.user_id == user.user_id)).scalars()}
    if user.site_id is not None:
        ids.add(user.site_id)
    return ids


def bu_site_ids(db: Session, business_unit_id: uuid.UUID | None) -> set[uuid.UUID]:
    if business_unit_id is None:
        return set()
    return set(db.execute(select(Site.site_id).where(Site.business_unit_id == business_unit_id)).scalars())


def visible_site_ids(db: Session, user: UsvUser) -> set[uuid.UUID] | None:
    if user.role in CUSTOMER_WIDE_ROLES:
        return None
    if user.role == USV_BU_ADMIN:
        return bu_site_ids(db, user.business_unit_id)
    return assigned_site_ids(db, user)


def can_view_site(db: Session, user: UsvUser, site_id: uuid.UUID) -> bool:
    visible = visible_site_ids(db, user)
    return visible is None or site_id in visible


def can_manage_site(db: Session, user: UsvUser, site_id: uuid.UUID) -> bool:
    """Admin actions on a site (tokens, downtime, limits, confirming a missing
    asset): customer-wide admins anywhere, a BU admin in their BU, a site
    admin on their own sites."""
    if user.role in CUSTOMER_ADMIN_ROLES:
        return True
    if user.role == USV_BU_ADMIN:
        site = db.get(Site, site_id)
        return site is not None and site.business_unit_id == user.business_unit_id
    if user.role == USV_SITE_ADMIN:
        return site_id in assigned_site_ids(db, user)
    return False


def can_manage_business_unit(user: UsvUser, business_unit_id: uuid.UUID) -> bool:
    if user.role in CUSTOMER_ADMIN_ROLES:
        return True
    return user.role == USV_BU_ADMIN and user.business_unit_id == business_unit_id


def narrow(requested: list[uuid.UUID] | None, visible: set[uuid.UUID] | None) -> list[uuid.UUID] | None:
    """Intersects a list filter (None = everything) with what the caller may see."""
    if visible is None:
        return requested
    if requested is None:
        return list(visible)
    return [s for s in requested if s in visible]
