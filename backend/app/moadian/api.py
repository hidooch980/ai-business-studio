from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent
from backend.app.moadian.models import MoadianConnection

router = APIRouter(prefix="/tax/moadian", tags=["moadian-tax"])
MemoryUid = Annotated[str, StringConstraints(strip_whitespace=True, min_length=6, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
TaxpayerIdentifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
SecretReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=200, pattern=r"^secret://[A-Za-z0-9._/-]+$")]
ProviderCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]+$")]


class MoadianConnectionRequest(BaseModel):
    tax_memory_uid: MemoryUid
    taxpayer_identifier: TaxpayerIdentifier
    submission_mode: Literal["direct", "tsp"]
    provider_code: ProviderCode | None = None
    environment: Literal["sandbox", "production"] = "sandbox"
    private_key_secret_ref: SecretReference | None = None
    certificate_secret_ref: SecretReference | None = None
    provider_credential_secret_ref: SecretReference | None = None
    is_enabled: bool = False

    @model_validator(mode="after")
    def validate_mode_credentials(self) -> "MoadianConnectionRequest":
        if self.submission_mode == "direct":
            if self.provider_code or self.provider_credential_secret_ref:
                raise ValueError("Direct mode cannot contain TSP provider credentials")
            if self.is_enabled and not (self.private_key_secret_ref and self.certificate_secret_ref):
                raise ValueError("Direct mode requires private-key and certificate secret references before enabling")
        else:
            if self.private_key_secret_ref or self.certificate_secret_ref:
                raise ValueError("TSP mode must not store taxpayer signing-key references")
            if self.is_enabled and not (self.provider_code and self.provider_credential_secret_ref):
                raise ValueError("TSP mode requires a provider code and provider credential reference before enabling")
        return self


def _serialize(item: MoadianConnection) -> dict:
    direct = item.submission_mode == "direct"
    return {
        "id": str(item.id),
        "tax_memory_uid": item.tax_memory_uid,
        "taxpayer_identifier": item.taxpayer_identifier,
        "submission_mode": item.submission_mode,
        "provider_code": item.provider_code,
        "environment": item.environment,
        "is_enabled": item.is_enabled,
        "credentials_configured": (
            bool(item.private_key_secret_ref and item.certificate_secret_ref)
            if direct else bool(item.provider_code and item.provider_credential_secret_ref)
        ),
        "transport_status": "awaiting_provider_adapter",
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _audit(db: Session, principal: TenantPrincipal, action: str, item: MoadianConnection) -> None:
    db.add(AuditEvent(
        tenant_id=principal.tenant.id,
        actor_user_id=principal.user.id,
        action=action,
        resource_type="moadian_connection",
        resource_id=str(item.id),
        outcome="success",
    ))


@router.get("/connections")
def list_connections(
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    db: Session = Depends(get_db_session),
) -> dict:
    items = db.scalars(
        select(MoadianConnection)
        .where(MoadianConnection.tenant_id == principal.tenant.id)
        .order_by(MoadianConnection.tax_memory_uid)
    ).all()
    return {"items": [_serialize(item) for item in items]}


@router.put("/connections")
def upsert_connection(
    payload: MoadianConnectionRequest,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    item = db.scalar(
        select(MoadianConnection).where(
            MoadianConnection.tenant_id == principal.tenant.id,
            MoadianConnection.tax_memory_uid == payload.tax_memory_uid,
        ).with_for_update()
    )
    values = payload.model_dump()
    if item is None:
        item = MoadianConnection(
            tenant_id=principal.tenant.id,
            created_by_user_id=principal.user.id,
            updated_by_user_id=principal.user.id,
            **values,
        )
        db.add(item)
        action = "tax.moadian_connection_created"
    else:
        for field, value in values.items():
            setattr(item, field, value)
        item.updated_by_user_id = principal.user.id
        action = "tax.moadian_connection_updated"
    _audit(db, principal, action, item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A Moadian connection with this tax memory UID already exists",
        ) from exc
    db.refresh(item)
    return _serialize(item)


@router.post("/connections/{connection_id}/disable")
def disable_connection(
    connection_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    item = db.scalar(
        select(MoadianConnection).where(
            MoadianConnection.id == connection_id,
            MoadianConnection.tenant_id == principal.tenant.id,
        ).with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Moadian connection not found")
    item.is_enabled = False
    item.updated_by_user_id = principal.user.id
    _audit(db, principal, "tax.moadian_connection_disabled", item)
    db.commit()
    db.refresh(item)
    return _serialize(item)
