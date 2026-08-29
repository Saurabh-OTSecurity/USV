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
