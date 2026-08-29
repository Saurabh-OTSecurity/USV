from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.database import engine

router = APIRouter()


@router.get("/health")
def health_check(response: Response):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy", "service": "usv-backend", "database": "healthy"}
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "service": "usv-backend", "database": "unavailable"}
