from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent, FinancialAccount

router = APIRouter(prefix="/finance/accounts", tags=["finance-accounts"])

AccountCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=32,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
AccountName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
AccountType = Literal["asset", "liability", "equity", "income", "expense"]


class AccountCreateRequest(BaseModel):
    code: AccountCode
    name: AccountName
    account_type: AccountType
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    parent_account_id: UUID | None = None


class AccountUpdateRequest(BaseModel):
    name: AccountName | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "AccountUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one account field must be supplied")
        return self


def _normal_balance(account_type: str) -> str:
    return "debit" if account_type in {"asset", "expense"} else "credit"


def _serialize_account(item: FinancialAccount) -> dict:
    return {
        "id": str(item.id),
        "tenant_id": str(item.tenant_id),
        "code": item.code,
        "name": item.name,
        "account_type": item.account_type,
        "normal_balance": _normal_balance(item.account_type),
        "description": item.description,
        "parent_account_id": str(item.parent_account_id) if item.parent_account_id else None,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _audit(db: Session, principal: TenantPrincipal, action: str, account: FinancialAccount) -> None:
    db.add(
        AuditEvent(
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            action=action,
            resource_type="financial_account",
            resource_id=str(account.id),
            outcome="success",
        )
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreateRequest,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    if payload.parent_account_id is not None:
        parent = db.scalar(
            select(FinancialAccount).where(
                FinancialAccount.id == payload.parent_account_id,
                FinancialAccount.tenant_id == principal.tenant.id,
                FinancialAccount.is_active.is_(True),
            )
        )
        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active parent account not found")
        if parent.account_type != payload.account_type:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Parent and child accounts must have the same account type",
            )
    account = FinancialAccount(
        tenant_id=principal.tenant.id,
        code=payload.code,
        name=payload.name,
        account_type=payload.account_type,
        description=payload.description,
        parent_account_id=payload.parent_account_id,
        created_by_user_id=principal.user.id,
    )
    db.add(account)
    try:
        db.flush()
        _audit(db, principal, "finance.account_created", account)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account code already exists in this tenant") from exc
    db.refresh(account)
    return _serialize_account(account)


@router.get("")
def list_accounts(
    principal: TenantPrincipal = Depends(require_permission("finance.read")),
    db: Session = Depends(get_db_session),
    account_type: AccountType | None = None,
    active_only: bool = True,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(FinancialAccount).where(FinancialAccount.tenant_id == principal.tenant.id)
    if account_type is not None:
        statement = statement.where(FinancialAccount.account_type == account_type)
    if active_only:
        statement = statement.where(FinancialAccount.is_active.is_(True))
    items = db.scalars(
        statement.order_by(FinancialAccount.code, FinancialAccount.id).offset(offset).limit(limit)
    ).all()
    return {"items": [_serialize_account(item) for item in items], "limit": limit, "offset": offset}


@router.patch("/{account_id}")
def update_account(
    account_id: UUID,
    payload: AccountUpdateRequest,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    account = db.scalar(
        select(FinancialAccount)
        .where(FinancialAccount.id == account_id, FinancialAccount.tenant_id == principal.tenant.id)
        .with_for_update()
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if "name" in payload.model_fields_set and payload.name is not None:
        account.name = payload.name
    if "description" in payload.model_fields_set:
        account.description = payload.description
    if payload.is_active is False and account.is_active:
        active_child = db.scalar(
            select(FinancialAccount.id).where(
                FinancialAccount.tenant_id == principal.tenant.id,
                FinancialAccount.parent_account_id == account.id,
                FinancialAccount.is_active.is_(True),
            ).limit(1)
        )
        if active_child is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with active child accounts cannot be deactivated",
            )
    if payload.is_active is True and account.parent_account_id is not None:
        parent_active = db.scalar(
            select(FinancialAccount.id).where(
                FinancialAccount.id == account.parent_account_id,
                FinancialAccount.tenant_id == principal.tenant.id,
                FinancialAccount.is_active.is_(True),
            )
        )
        if parent_active is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account cannot be activated while its parent is inactive",
            )
    if payload.is_active is not None:
        account.is_active = payload.is_active
    account.updated_at = datetime.now(UTC)
    _audit(db, principal, "finance.account_updated", account)
    db.commit()
    db.refresh(account)
    return _serialize_account(account)
