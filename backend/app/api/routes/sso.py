"""Single sign-on into Tribot (USV O&M Manual section 10). See
app/services/sso.py for the assertion format, role mapping and directory."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.ingest import _record_refusal, get_ingest_db
from app.core.rbac import get_current_user, get_db
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.services import sso
from app.services.audit_service import AuditService
from app.services.ingestion_token_service import IngestionTokenService, InvalidIngestionCredentialError

router = APIRouter(prefix="/api/v1/sso", tags=["sso"])
_bearer = HTTPBearer(auto_error=False)


@router.get("/public-key")
def sso_public_key() -> dict:
    """USV's assertion-verification key. Public by design; Tribots also
    receive it with every directory poll."""
    return sso.public_key()


class AssertionRequest(BaseModel):
    site_id: uuid.UUID


@router.post("/tribot/assertion")
def tribot_assertion(payload: AssertionRequest, db: Session = Depends(get_db),
                     current_user: UsvUser = Depends(get_current_user)) -> dict:
    site = db.get(Site, payload.site_id)
    if site is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "SITE_NOT_FOUND", "message": "Site not found"}})
    try:
        result = sso.issue_assertion(db, current_user, site)
    except sso.SsoRefused as e:
        AuditService(db).record(event_type="sso_refused", actor_user_id=current_user.user_id, target_type="site",
                                target_id=site.site_id, result="failure", detail={"reason": str(e)})
        raise HTTPException(status_code=403, detail={"error": {"code": "SSO_REFUSED", "message": str(e)}})
    AuditService(db).record(event_type="sso_assertion_issued", actor_user_id=current_user.user_id, target_type="site",
                            target_id=site.site_id, result="success", detail={"role": result["role"]})
    return result


@router.get("/tribot/directory")
def tribot_directory(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
                     db: Session = Depends(get_ingest_db)) -> dict:
    """Polled by each Tribot (outbound, with its ingestion token): who may
    sign in there, revoked sessions, break-glass hash, policy, approvers."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Ingestion token required"}})
    try:
        token = IngestionTokenService(db).authenticate(credentials.credentials)
    except InvalidIngestionCredentialError as error:
        _record_refusal(db, request, error)
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid ingestion credential"}})
    return sso.directory(db, db.get(Site, token.site_id))
