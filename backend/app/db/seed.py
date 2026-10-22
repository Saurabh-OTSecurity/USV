from passlib.context import CryptContext

from app.core.database import SessionLocal
from app.models import AuditLog, BusinessUnit, Integration, Site, SyncState, Tenant, Usv, UsvUser  # noqa: F401

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SITE_CODE = "SITE-001"
USV_CODE = "USV-001"

INTEGRATIONS = [
    {"integration_type": "asset_source", "name": "Tribot", "provider": "tribot", "is_fixed_engine": False},
    {"integration_type": "asset_source", "name": "Claroty", "provider": "claroty", "is_fixed_engine": False},
    {"integration_type": "asset_source", "name": "Nozomi", "provider": "nozomi", "is_fixed_engine": False},
    {"integration_type": "siem", "name": "Wazuh Manager", "provider": "wazuh", "is_fixed_engine": True},
    {"integration_type": "siem", "name": "Wazuh Indexer", "provider": "wazuh", "is_fixed_engine": True},
    {"integration_type": "incident_response", "name": "Incident Response", "provider": "tribastion_ir", "is_fixed_engine": True},
    {"integration_type": "ecc", "name": "ECC", "provider": "tribastion_ecc", "is_fixed_engine": True},
]

USERS = [
    {"username": "platform.admin", "role": "usv_platform_admin", "display_name": "Platform Admin", "password": "DevOnly!PlatformAdmin1"},
    {"username": "site.admin", "role": "usv_site_admin", "display_name": "Site Admin", "password": "DevOnly!SiteAdmin1"},
    {"username": "l2.analyst", "role": "usv_l2_analyst", "display_name": "L2 Analyst", "password": "DevOnly!L2Analyst1"},
    {"username": "l1.operator", "role": "usv_l1_operator", "display_name": "L1 Operator", "password": "DevOnly!L1Operator1"},
    {"username": "auditor.user", "role": "usv_auditor", "display_name": "Auditor", "password": "DevOnly!Auditor1"},
    {"username": "viewer.user", "role": "usv_viewer", "display_name": "Viewer", "password": "DevOnly!Viewer1"},
]


def seed() -> None:
    session = SessionLocal()
    try:
        # T-1: every Site needs a Business Unit. v006's migration already
        # backfills a "Default Tenant" / "Default Business Unit" pair for an
        # already-populated database; on a genuinely fresh database (schema
        # created but v006 ran with zero sites, or tests that rebuild from
        # scratch) that pair still exists from the migration, so reuse it
        # rather than creating a second one here.
        tenant = session.query(Tenant).first()
        if tenant is None:
            tenant = Tenant(name="Default Tenant", status="active")
            session.add(tenant)
            session.flush()

        business_unit = session.query(BusinessUnit).filter_by(tenant_id=tenant.tenant_id).first()
        if business_unit is None:
            business_unit = BusinessUnit(tenant_id=tenant.tenant_id, name="Default Business Unit", status="active")
            session.add(business_unit)
            session.flush()

        site = session.query(Site).filter_by(site_code=SITE_CODE).one_or_none()
        if site is None:
            site = Site(
                site_code=SITE_CODE,
                name="Demo Manufacturing Plant",
                description="Development seed site",
                timezone="UTC",
                criticality="medium",
                status="active",
                business_unit_id=business_unit.business_unit_id,
            )
            session.add(site)
            session.flush()

        usv = session.query(Usv).filter_by(usv_code=USV_CODE).one_or_none()
        if usv is None:
            usv = Usv(
                site_id=site.site_id,
                usv_code=USV_CODE,
                hostname="usv-demo-01",
                version="0.1.0",
                status="active",
            )
            session.add(usv)

        for integ in INTEGRATIONS:
            existing = session.query(Integration).filter_by(name=integ["name"]).one_or_none()
            if existing is None:
                session.add(
                    Integration(
                        site_id=site.site_id,
                        integration_type=integ["integration_type"],
                        name=integ["name"],
                        provider=integ["provider"],
                        is_fixed_engine=integ["is_fixed_engine"],
                        status="configured",
                    )
                )

        for user in USERS:
            existing = session.query(UsvUser).filter_by(username=user["username"]).one_or_none()
            if existing is None:
                session.add(
                    UsvUser(
                        site_id=site.site_id,
                        username=user["username"],
                        password_hash=pwd_context.hash(user["password"]),
                        role=user["role"],
                        display_name=user["display_name"],
                        status="active",
                    )
                )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
    print("Seed data loaded.")
