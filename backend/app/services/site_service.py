import uuid

from sqlalchemy.orm import Session

from app.models.site import Site
from app.repositories.site_repository import SiteRepository


class SiteService:
    def __init__(self, db: Session):
        self.repository = SiteRepository(db)

    def list_sites(self) -> list[Site]:
        return self.repository.list_all()

    def get_site(self, site_id: uuid.UUID) -> Site | None:
        return self.repository.get_by_id(site_id)
