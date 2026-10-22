import uuid

from sqlalchemy.orm import Session

from app.models.site import Site
from app.repositories.site_repository import SiteRepository


class SiteCodeAlreadyExistsError(Exception):
    pass


class SiteService:
    def __init__(self, db: Session):
        self.repository = SiteRepository(db)

    def list_sites(self) -> list[Site]:
        return self.repository.list_all()

    def get_site(self, site_id: uuid.UUID) -> Site | None:
        return self.repository.get_by_id(site_id)

    def create_site(
        self,
        *,
        site_code: str,
        name: str,
        business_unit_id: uuid.UUID,
        description: str | None = None,
        timezone: str | None = None,
        criticality: str | None = None,
        tribot_url: str | None = None,
    ) -> Site:
        if self.repository.get_by_code(site_code) is not None:
            raise SiteCodeAlreadyExistsError(site_code)
        return self.repository.create(
            Site(
                site_code=site_code,
                name=name,
                business_unit_id=business_unit_id,
                description=description,
                timezone=timezone,
                criticality=criticality,
                tribot_url=tribot_url,
                status="active",
            )
        )
