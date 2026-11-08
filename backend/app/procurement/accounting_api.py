from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent, FinancialAccount
from backend.app.procurement.models import ProcurementAccountingSettings

router = APIRouter(prefix="/procurement/accounting-settings", tags=["purchase-accounting"])

AccountCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"),
]


class ProcurementAccountingSettingsRequest(BaseModel):
    inventory_account_code: AccountCode
    grni_account_code: AccountCode
    ap_account_code: AccountCode
    cash_account_code: AccountCode
    base_currency: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)] = "USD"

    @model_validator(mode="after")
    def validate_codes(self) -> "ProcurementAccountingSettingsRequest":
        codes = [
            self.inventory_account_code.upper(),
            self.grni_account_code.upper(),
            self.ap_account_code.upper(),
            self.cash_account_code.upper(),
        ]
        if len(set(codes)) != 4:
            raise ValueError("Each procurement accounting role must use a different account")
        if not self.base_currency.isascii() or not self.base_currency.isalpha():
            raise ValueError("Base currency must be a three-letter code")
        return self


def _serialize(item: ProcurementAccountingSettings) -> dict:
    return {
        "inventory_account_code": item.inventory_account_code,
        "grni_account_code": item.grni_account_code,
        "ap_account_code": item.ap_account_code,
        "cash_account_code": item.cash_account_code,
        "base_currency": item.base_currency,
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("")
def get_procurement_accounting_settings(
    principal: TenantPrincipal = Depends(require_permission("finance.read")),
    db: Session = Depends(get_db_session),
) -> dict:
    item = db.scalar(select(ProcurementAccountingSettings).where(
        ProcurementAccountingSettings.tenant_id == principal.tenant.id
    ))
    if item is None:
        return {"configured": False, "settings": None}
    return {"configured": True, "settings": _serialize(item)}


@router.put("", status_code=status.HTTP_200_OK)
def upsert_procurement_accounting_settings(
    payload: ProcurementAccountingSettingsRequest,
    principal: TenantPrincipal = Depends(require_permission("finance.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    expected_types = {
        payload.inventory_account_code.upper(): "asset",
        payload.grni_account_code.upper(): "liability",
        payload.ap_account_code.upper(): "liability",
        payload.cash_account_code.upper(): "asset",
    }
    accounts = db.scalars(select(FinancialAccount).where(
        FinancialAccount.tenant_id == principal.tenant.id,
        FinancialAccount.code.in_(expected_types),
        FinancialAccount.is_active.is_(True),
    ).with_for_update()).all()
    by_code = {account.code: account for account in accounts}
    missing = sorted(set(expected_types) - set(by_code))
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown or inactive account code(s): {', '.join(missing)}")
    wrong_types = sorted(
        code for code, account_type in expected_types.items()
        if by_code[code].account_type != account_type
    )
    if wrong_types:
        raise HTTPException(status_code=422, detail=f"Account type is invalid for code(s): {', '.join(wrong_types)}")

    item = db.scalar(select(ProcurementAccountingSettings).where(
        ProcurementAccountingSettings.tenant_id == principal.tenant.id
    ).with_for_update())
    now = datetime.now(UTC)
    values = {
        "inventory_account_code": payload.inventory_account_code.upper(),
        "grni_account_code": payload.grni_account_code.upper(),
        "ap_account_code": payload.ap_account_code.upper(),
        "cash_account_code": payload.cash_account_code.upper(),
        "base_currency": payload.base_currency.upper(),
        "updated_by_user_id": principal.user.id,
        "updated_at": now,
    }
    if item is None:
        item = ProcurementAccountingSettings(
            tenant_id=principal.tenant.id,
            created_by_user_id=principal.user.id,
            created_at=now,
            **values,
        )
        db.add(item)
    else:
        for key, value in values.items():
            setattr(item, key, value)
    db.add(AuditEvent(
        tenant_id=principal.tenant.id,
        actor_user_id=principal.user.id,
        action="procurement.accounting_settings_updated",
        resource_type="procurement_accounting_settings",
        resource_id=str(item.id),
        outcome="success",
    ))
    db.commit()
    db.refresh(item)
    return {"configured": True, "settings": _serialize(item)}
