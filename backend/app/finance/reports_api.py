from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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



@router.get("/general-ledger/{account_id}")
def general_ledger(
    account_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("finance.read")),
    db: Session = Depends(get_db_session),
    currency: CurrencyCode = "USD",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must be on or before end_date",
        )
    normalized_currency = currency.upper()
    account = db.scalar(
        select(FinancialAccount).where(
            FinancialAccount.id == account_id,
            FinancialAccount.tenant_id == principal.tenant.id,
        )
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Financial account not found")
    normal_balance = "debit" if account.account_type in {"asset", "expense"} else "credit"
    base_filters = [
        JournalLine.tenant_id == principal.tenant.id,
        JournalLine.financial_account_id == account.id,
        JournalEntry.tenant_id == principal.tenant.id,
        JournalEntry.currency == normalized_currency,
    ]
    opening_debit = 0
    opening_credit = 0
    if start_date is not None:
        opening = db.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit_minor), 0),
                func.coalesce(func.sum(JournalLine.credit_minor), 0),
            )
            .join(
                JournalEntry,
                (JournalEntry.id == JournalLine.journal_entry_id)
                & (JournalEntry.tenant_id == JournalLine.tenant_id),
            )
            .where(*base_filters, JournalEntry.posting_date < start_date)
        ).one()
        opening_debit, opening_credit = int(opening[0]), int(opening[1])
    running_balance = (
        opening_debit - opening_credit
        if normal_balance == "debit"
        else opening_credit - opening_debit
    )
    statement = (
        select(JournalLine, JournalEntry)
        .join(
            JournalEntry,
            (JournalEntry.id == JournalLine.journal_entry_id)
            & (JournalEntry.tenant_id == JournalLine.tenant_id),
        )
        .where(*base_filters)
    )
    if start_date is not None:
        statement = statement.where(JournalEntry.posting_date >= start_date)
    if end_date is not None:
        statement = statement.where(JournalEntry.posting_date <= end_date)
    rows = db.execute(
        statement.order_by(
            JournalEntry.posting_date,
            JournalEntry.created_at,
            JournalEntry.id,
            JournalLine.line_number,
        )
    ).all()
    items = []
    for line, entry in rows:
        debit = int(line.debit_minor)
        credit = int(line.credit_minor)
        running_balance += debit - credit if normal_balance == "debit" else credit - debit
        items.append(
            {
                "journal_entry_id": str(entry.id),
                "posting_date": entry.posting_date.isoformat() if entry.posting_date else None,
                "description": entry.description,
                "memo": line.memo,
                "debit_minor": debit,
                "credit_minor": credit,
                "running_balance_minor": running_balance,
            }
        )
    return {
        "account_id": str(account.id),
        "account_code": account.code,
        "account_name": account.name,
        "account_type": account.account_type,
        "normal_balance": normal_balance,
        "currency": normalized_currency,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "opening_balance_minor": (
            opening_debit - opening_credit
            if normal_balance == "debit"
            else opening_credit - opening_debit
        ),
        "items": items,
        "closing_balance_minor": running_balance,
    }
