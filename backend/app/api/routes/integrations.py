import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user, get_db
from app.models.usv_user import UsvUser
from app.schemas.integration import IntegrationResponse
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "INTEGRATION_NOT_FOUND", "message": "Integration not found"}},
    )


@router.get("", response_model=list[IntegrationResponse])
def list_integrations(
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[IntegrationResponse]:
    integrations = IntegrationService(db).list_integrations()
    return [IntegrationResponse.model_validate(integration) for integration in integrations]


@router.get("/{integration_id}", response_model=IntegrationResponse)
def get_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> IntegrationResponse:
    integration = IntegrationService(db).get_integration(integration_id)
    if integration is None:
        raise _not_found()
    return IntegrationResponse.model_validate(integration)
