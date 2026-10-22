import uuid

from sqlalchemy.orm import Session

from app.models.site import Site


class SiteRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[Site]:
        return self.db.query(Site).order_by(Site.site_code).all()

    def get_by_id(self, site_id: uuid.UUID) -> Site | None:
        return self.db.get(Site, site_id)

    def get_by_code(self, site_code: str) -> Site | None:
        return self.db.query(Site).filter_by(site_code=site_code).one_or_none()

    def create(self, site: Site) -> Site:
        self.db.add(site)
        self.db.commit()
        self.db.refresh(site)
        return site
