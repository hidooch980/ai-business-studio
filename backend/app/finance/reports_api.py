from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_permission
from backend.app.identity.models import FinancialAccount, JournalEntry, JournalLine

router = APIRouter(prefix="/finance/reports", tags=["finance-reports"])

CurrencyCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$"),
]


@router.get("/trial-balance")
def trial_balance(
    principal: TenantPrincipal = Depends(require_permission("finance.read")),
    db: Session = Depends(get_db_session),
    as_of: date = Query(default_factory=date.today),
    currency: CurrencyCode = "USD",
) -> dict:
    normalized_currency = currency.upper()
    totals = (
        select(
            JournalLine.financial_account_id.label("account_id"),
            func.coalesce(func.sum(JournalLine.debit_minor), 0).label("debit_total_minor"),
            func.coalesce(func.sum(JournalLine.credit_minor), 0).label("credit_total_minor"),
        )
        .join(
            JournalEntry,
            (JournalEntry.id == JournalLine.journal_entry_id)
            & (JournalEntry.tenant_id == JournalLine.tenant_id),
        )
        .where(
            JournalLine.tenant_id == principal.tenant.id,
            JournalEntry.tenant_id == principal.tenant.id,
            JournalEntry.posting_date <= as_of,
            JournalEntry.currency == normalized_currency,
            JournalLine.financial_account_id.is_not(None),
        )
        .group_by(JournalLine.financial_account_id)
        .subquery()
    )
    rows = db.execute(
        select(
            FinancialAccount.id,
            FinancialAccount.code,
            FinancialAccount.name,
            FinancialAccount.account_type,
            totals.c.debit_total_minor,
            totals.c.credit_total_minor,
        )
        .outerjoin(totals, totals.c.account_id == FinancialAccount.id)
        .where(FinancialAccount.tenant_id == principal.tenant.id)
        .order_by(FinancialAccount.code, FinancialAccount.id)
    ).all()
    items = []
    for row in rows:
        debit = int(row.debit_total_minor or 0)
        credit = int(row.credit_total_minor or 0)
        normal_balance = "debit" if row.account_type in {"asset", "expense"} else "credit"
        balance = debit - credit if normal_balance == "debit" else credit - debit
        items.append(
            {
                "account_id": str(row.id),
                "account_code": row.code,
                "account_name": row.name,
                "account_type": row.account_type,
                "normal_balance": normal_balance,
                "debit_minor": debit,
                "credit_minor": credit,
                "balance_minor": balance,
            }
        )
    unmapped_lines = db.scalar(
        select(func.count(JournalLine.id))
        .join(
            JournalEntry,
            (JournalEntry.id == JournalLine.journal_entry_id)
            & (JournalEntry.tenant_id == JournalLine.tenant_id),
        )
        .where(
            JournalLine.tenant_id == principal.tenant.id,
            JournalLine.financial_account_id.is_(None),
            JournalEntry.posting_date <= as_of,
            JournalEntry.currency == normalized_currency,
        )
    ) or 0
    total_debits = sum(item["debit_minor"] for item in items)
    total_credits = sum(item["credit_minor"] for item in items)
    return {
        "as_of": as_of.isoformat(),
        "currency": normalized_currency,
        "items": items,
        "total_debits_minor": total_debits,
        "total_credits_minor": total_credits,
        "is_balanced": total_debits == total_credits and unmapped_lines == 0,
        "unmapped_journal_lines": int(unmapped_lines),
    }
