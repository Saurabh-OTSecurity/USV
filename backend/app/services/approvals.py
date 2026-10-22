"""Who approves what (USV O&M Manual section 11).

The approver is always one level up, never the person themselves:

  person who forgot      first approver       if unavailable (backup)
  viewer / engineer      site admin           BU admin
  site admin             BU admin             customer admin
  BU admin               customer admin       platform admin
  customer admin         platform admin       a second platform admin
  platform admin         another platform admin (two approvals required)

Named approvers (the approver table, per level and scope, with backups) take
precedence; when a level has none named, everyone holding that level's admin
role for the right scope is eligible, so a request is never stranded.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, USV_SITE_ADMIN
from app.models.identity import Approver
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.models.usv_user_site import UsvUserSite
from app.services.access_scope import assigned_site_ids

LEVEL_ROLE = {
    "site": USV_SITE_ADMIN,
    "business_unit": USV_BU_ADMIN,
    "customer": USV_CUSTOMER_ADMIN,
    "platform": USV_PLATFORM_ADMIN,
}


def _site_bu(db: Session, site_ids: set) -> set:
    if not site_ids:
        return set()
    return set(db.execute(select(Site.business_unit_id).where(Site.site_id.in_(site_ids))).scalars())


def _scope_ids(db: Session, person: UsvUser, level: str) -> set:
    if level == "site":
        return assigned_site_ids(db, person)
    if level == "business_unit":
        return {person.business_unit_id} if person.business_unit_id else _site_bu(db, assigned_site_ids(db, person))
    return {None}


def _named(db: Session, level: str, scopes: set, backup: bool) -> list[uuid.UUID]:
    q = select(Approver.user_id).where(Approver.level == level, Approver.is_backup.is_(backup))
    if scopes != {None}:
        q = q.where(Approver.scope_id.in_([s for s in scopes if s is not None]))
    else:
        q = q.where(Approver.scope_id.is_(None))
    return list(db.execute(q).scalars())


def _role_holders(db: Session, level: str, scopes: set) -> list[uuid.UUID]:
    role = LEVEL_ROLE[level]
    users = db.execute(select(UsvUser).where(UsvUser.role == role, UsvUser.status == "active")).scalars().all()
    if level == "site":
        holders = []
        for u in users:
            if u.site_id in scopes or db.execute(select(UsvUserSite).where(
                    UsvUserSite.user_id == u.user_id, UsvUserSite.site_id.in_(scopes))).first():
                holders.append(u.user_id)
        return holders
    if level == "business_unit":
        return [u.user_id for u in users if u.business_unit_id in scopes]
    return [u.user_id for u in users]


def _eligible(db: Session, person: UsvUser, level: str, backup: bool) -> list[uuid.UUID]:
    scopes = _scope_ids(db, person, level)
    if scopes in (set(), {None}) and level in ("site", "business_unit"):
        return []
    ids = _named(db, level, scopes, backup)
    if not ids and not backup:
        ids = _role_holders(db, level, scopes)
    return [i for i in ids if i != person.user_id]


def chain_for(person: UsvUser) -> tuple[list[str], int]:
    """(levels in order: first, then backups; approvals required)."""
    role = person.role
    if role == USV_PLATFORM_ADMIN:
        return ["platform"], 2
    if role == USV_CUSTOMER_ADMIN:
        return ["platform"], 1
    if role == USV_BU_ADMIN:
        return ["customer", "platform"], 1
    if role == USV_SITE_ADMIN:
        return ["business_unit", "customer", "platform"], 1
    return ["site", "business_unit", "customer", "platform"], 1


def approvers_for(db: Session, person: UsvUser) -> tuple[list[uuid.UUID], list[uuid.UUID], int]:
    """(first approvers, backups, approvals required). The first level that
    has anyone is the primary; the next level with anyone is the backup."""
    levels, required = chain_for(person)
    found: list[list[uuid.UUID]] = []
    for level in levels:
        primary = _eligible(db, person, level, backup=False)
        if primary:
            found.append(primary)
            named_backups = _eligible(db, person, level, backup=True)
            if named_backups:
                found.append(named_backups)
        if len(found) >= 2:
            break
    primary = found[0] if found else []
    backups = [u for u in (found[1] if len(found) > 1 else []) if u not in primary]
    return primary, backups, required


def may_approve(db: Session, approver: UsvUser, person: UsvUser, escalated: bool) -> bool:
    if approver.user_id == person.user_id:
        return False
    primary, backups, _ = approvers_for(db, person)
    return approver.user_id in primary or (escalated and approver.user_id in backups)
