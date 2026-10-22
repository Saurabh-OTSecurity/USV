import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.tenancy import register_token_route, tenant_id_from_authorization
from app.core.rbac import (
    USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, USV_SITE_ADMIN, get_current_user, get_db, require_role,
)
from app.services.access_scope import can_manage_site, can_view_site
from app.models.usv_user import UsvUser
from app.schemas.ingestion import IngestionTokenIssuedResponse, IngestionTokenResponse
from app.services.ingestion_token_service import IngestionTokenService, SiteNotFoundError
from app.services.monitoring import rules as monitoring_rules

_TOKEN_ADMINS = (USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_BU_ADMIN, USV_SITE_ADMIN)


def _forbidden_site() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": {"code": "SITE_NOT_FOUND", "message": "Site not found"}})


router = APIRouter(prefix="/api/v1/sites/{site_id}/ingestion-tokens", tags=["ingestion-tokens"])


def _site_not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "SITE_NOT_FOUND", "message": "Site not found"}},
    )


@router.get("", response_model=list[IngestionTokenResponse])
def list_ingestion_tokens(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[IngestionTokenResponse]:
    if not can_view_site(db, current_user, site_id):
        raise _forbidden_site()
    tokens = IngestionTokenService(db).list_for_site(site_id)
    return [IngestionTokenResponse.model_validate(t) for t in tokens]


@router.post("", response_model=IngestionTokenIssuedResponse, status_code=201)
def issue_ingestion_token(
    site_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(*_TOKEN_ADMINS)),
) -> IngestionTokenIssuedResponse:
    """Issue a new credential for this site's Tribot instance to push with.
    The returned `token` is shown exactly once -- store it in that Tribot
    instance's usv_push destination config immediately; it cannot be
    retrieved again (only re-issued as a new token)."""
    if not can_manage_site(db, current_user, site_id):
        raise _forbidden_site()
    try:
        token, plaintext = IngestionTokenService(db).issue_token(site_id)
    except SiteNotFoundError:
        raise _site_not_found()
    monitoring_rules.token_changed(db, site_id, "issued", token.token_id)
    db.commit()
    tenant_id = tenant_id_from_authorization(request.headers.get("authorization"))
    if tenant_id is not None:
        register_token_route(token.token_id, tenant_id)
    return IngestionTokenIssuedResponse(
        token_id=token.token_id,
        site_id=token.site_id,
        status=token.status,
        created_at=token.created_at,
        revoked_at=token.revoked_at,
        last_used_at=token.last_used_at,
        token=plaintext,
    )


@router.delete("/{token_id}", response_model=IngestionTokenResponse)
def revoke_ingestion_token(
    site_id: uuid.UUID,
    token_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(*_TOKEN_ADMINS)),
) -> IngestionTokenResponse:
    if not can_manage_site(db, current_user, site_id):
        raise _forbidden_site()
    token = IngestionTokenService(db).revoke(token_id)
    if token is None or token.site_id != site_id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "INGESTION_TOKEN_NOT_FOUND", "message": "Ingestion token not found"}},
        )
    monitoring_rules.token_changed(db, site_id, "revoked", token.token_id)
    db.commit()
    return IngestionTokenResponse.model_validate(token)
