from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent, FinancialPeriod, Tenant

router = APIRouter(prefix="/finance/periods", tags=["finance-periods"])

PeriodName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class PeriodCreateRequest(BaseModel):
    name: PeriodName
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self) -> "PeriodCreateRequest":
        if self.start_date > self.end_date:
            raise ValueError("Period start_date must be on or before end_date")
        return self


def _serialize_period(period: FinancialPeriod) -> dict:
    return {
        "id": str(period.id),
        "tenant_id": str(period.tenant_id),
        "name": period.name,
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
        "status": period.status,
        "closed_at": period.closed_at.isoformat() if period.closed_at else None,
        "created_at": period.created_at.isoformat(),
        "updated_at": period.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_period(
    payload: PeriodCreateRequest,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    tenant = db.scalar(select(Tenant).where(Tenant.id == principal.tenant.id).with_for_update())
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    overlap = db.scalar(
        select(FinancialPeriod.id)
        .where(
            FinancialPeriod.tenant_id == principal.tenant.id,
            FinancialPeriod.start_date <= payload.end_date,
            FinancialPeriod.end_date >= payload.start_date,
        )
        .limit(1)
    )
    if overlap is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Accounting periods cannot overlap within a tenant",
        )
    period = FinancialPeriod(
        tenant_id=principal.tenant.id,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="open",
        created_by_user_id=principal.user.id,
    )
    db.add(period)
    try:
        db.flush()
        db.add(
            AuditEvent(
                tenant_id=principal.tenant.id,
                actor_user_id=principal.user.id,
                action="finance.period_created",
                resource_type="financial_period",
                resource_id=str(period.id),
                outcome="success",
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Accounting period name already exists") from exc
    db.refresh(period)
    return _serialize_period(period)


@router.get("")
def list_periods(
    principal: TenantPrincipal = Depends(require_permission("finance.read")),
    db: Session = Depends(get_db_session),
    include_closed: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(FinancialPeriod).where(FinancialPeriod.tenant_id == principal.tenant.id)
    if not include_closed:
        statement = statement.where(FinancialPeriod.status == "open")
    items = db.scalars(
        statement.order_by(FinancialPeriod.start_date.desc(), FinancialPeriod.id).offset(offset).limit(limit)
    ).all()
    return {"items": [_serialize_period(item) for item in items], "limit": limit, "offset": offset}


@router.post("/{period_id}/close")
def close_period(
    period_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    period = db.scalar(
        select(FinancialPeriod)
        .where(
            FinancialPeriod.id == period_id,
            FinancialPeriod.tenant_id == principal.tenant.id,
        )
        .with_for_update()
    )
    if period is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Accounting period not found")
    if period.status == "closed":
        return _serialize_period(period)
    period.status = "closed"
    period.closed_by_user_id = principal.user.id
    period.closed_at = datetime.now(UTC)
    period.updated_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            action="finance.period_closed",
            resource_type="financial_period",
            resource_id=str(period.id),
            outcome="success",
        )
    )
    db.commit()
    db.refresh(period)
    return _serialize_period(period)
