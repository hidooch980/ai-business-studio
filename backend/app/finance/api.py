from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.finance.ledger import (
    AccountingPeriodConflictError,
    JournalConflictError,
    create_journal_entry,
    reverse_journal_entry,
    serialize_journal_entry,
)
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import JournalEntry

router = APIRouter(prefix="/finance/journals", tags=["finance-ledger"])

AccountCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class JournalLineInput(BaseModel):
    account_code: AccountCode
    memo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    debit_minor: int = Field(default=0, ge=0, le=2_147_483_647)
    credit_minor: int = Field(default=0, ge=0, le=2_147_483_647)


class JournalCreateRequest(BaseModel):
    posting_date: date | None = None
    currency: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    lines: list[JournalLineInput] = Field(min_length=2, max_length=100)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_journal(
    payload: JournalCreateRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        entry, created = create_journal_entry(
            db,
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            idempotency_key=idempotency_key,
            currency=payload.currency,
            description=payload.description,
            lines=[line.model_dump() for line in payload.lines],
            posting_date=payload.posting_date,
        )
    except (JournalConflictError, AccountingPeriodConflictError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {**serialize_journal_entry(db, entry), "created": created}


@router.get("")
def list_journals(
    principal: TenantPrincipal = Depends(require_permission("finance.read")),
    db: Session = Depends(get_db_session),
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = None,
) -> dict:
    statement = select(JournalEntry).where(JournalEntry.tenant_id == principal.tenant.id)
    if before is not None:
        statement = statement.where(JournalEntry.created_at < before)
    entries = db.scalars(
        statement.order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc()).limit(limit)
    ).all()
    return {"items": [serialize_journal_entry(db, entry) for entry in entries]}



@router.post("/{journal_entry_id}/reverse", status_code=status.HTTP_201_CREATED)
def reverse_journal(
    journal_entry_id: UUID,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
    ],
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    try:
        entry, created = reverse_journal_entry(
            db,
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            journal_entry_id=journal_entry_id,
            idempotency_key=idempotency_key,
        )
    except JournalConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Journal entry not found" else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return {**serialize_journal_entry(db, entry), "created": created, "reversal_of_id": str(journal_entry_id)}
