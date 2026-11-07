from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.identity.models import AuditEvent, JournalEntry, JournalLine


class JournalConflictError(ValueError):
    """Raised when an idempotency key is reused with different journal data."""


def _normalized_payload(currency: str, description: str, lines: list[dict]) -> dict:
    return {
        "currency": currency.upper(),
        "description": description.strip(),
        "lines": [
            {
                "account_code": item["account_code"].strip(),
                "memo": (item.get("memo") or "").strip() or None,
                "debit_minor": int(item.get("debit_minor", 0)),
                "credit_minor": int(item.get("credit_minor", 0)),
            }
            for item in lines
        ],
    }


def _request_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def create_journal_entry(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    idempotency_key: str,
    currency: str,
    description: str,
    lines: list[dict],
    reversal_of_id: UUID | None = None,
) -> tuple[JournalEntry, bool]:
    key = idempotency_key.strip()
    if not key or len(key) > 128:
        raise ValueError("Idempotency-Key must contain 1 to 128 characters")
    payload = _normalized_payload(currency, description, lines)
    if len(payload["currency"]) != 3 or not payload["currency"].isalpha() or not payload["currency"].isascii():
        raise ValueError("Currency must be a three-letter ISO-style code")
    if not payload["description"] or len(payload["description"]) > 500:
        raise ValueError("Description must contain 1 to 500 characters")
    normalized_lines = payload["lines"]
    if not 2 <= len(normalized_lines) <= 100:
        raise ValueError("A journal entry must contain between 2 and 100 lines")
    debit_total = 0
    credit_total = 0
    for item in normalized_lines:
        if not item["account_code"] or len(item["account_code"]) > 64:
            raise ValueError("Every line requires an account code of at most 64 characters")
        if item["memo"] is not None and len(item["memo"]) > 255:
            raise ValueError("Line memo must not exceed 255 characters")
        debit = item["debit_minor"]
        credit = item["credit_minor"]
        if debit < 0 or credit < 0 or (debit > 0) == (credit > 0):
            raise ValueError("Each line must have exactly one positive debit or credit amount")
        debit_total += debit
        credit_total += credit
        if debit_total > 2_147_483_647 or credit_total > 2_147_483_647:
            raise ValueError("Journal totals exceed the supported integer range")
    if debit_total == 0 or debit_total != credit_total:
        raise ValueError("Journal entry must balance: total debits must equal total credits")
    hash_payload = {**payload, "reversal_of_id": str(reversal_of_id) if reversal_of_id else None}
    digest = _request_hash(hash_payload)
    existing = db.scalar(
        select(JournalEntry).where(
            JournalEntry.tenant_id == tenant_id,
            JournalEntry.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise JournalConflictError("Idempotency-Key was already used for a different journal entry")
        return existing, False

    entry = JournalEntry(
        tenant_id=tenant_id,
        idempotency_key=key,
        request_hash=digest,
        reversal_of_id=reversal_of_id,
        currency=payload["currency"],
        description=payload["description"],
        debit_total_minor=debit_total,
        credit_total_minor=credit_total,
        created_by_user_id=actor_user_id,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raced = db.scalar(
            select(JournalEntry).where(
                JournalEntry.tenant_id == tenant_id,
                JournalEntry.idempotency_key == key,
            )
        )
        if raced is None and reversal_of_id is not None:
            raced = db.scalar(
                select(JournalEntry).where(
                    JournalEntry.tenant_id == tenant_id,
                    JournalEntry.reversal_of_id == reversal_of_id,
                )
            )
        if raced is None:
            raise
        if raced.idempotency_key != key or raced.request_hash != digest:
            raise JournalConflictError("Journal entry already has a different reversal or the key was reused")
        return raced, False
    db.add_all(
        [
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                line_number=index,
                account_code=item["account_code"],
                memo=item["memo"],
                debit_minor=item["debit_minor"],
                credit_minor=item["credit_minor"],
            )
            for index, item in enumerate(normalized_lines, start=1)
        ]
    )
    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="finance.journal_created",
            resource_type="journal_entry",
            resource_id=str(entry.id),
            outcome="success",
        )
    )
    db.commit()
    db.refresh(entry)
    return entry, True


def serialize_journal_entry(db: Session, entry: JournalEntry) -> dict:
    lines = db.scalars(
        select(JournalLine)
        .where(JournalLine.tenant_id == entry.tenant_id, JournalLine.journal_entry_id == entry.id)
        .order_by(JournalLine.line_number)
    ).all()
    return {
        "id": str(entry.id),
        "tenant_id": str(entry.tenant_id),
        "currency": entry.currency,
        "description": entry.description,
        "created_at": entry.created_at.isoformat(),
        "lines": [
            {
                "line_number": line.line_number,
                "account_code": line.account_code,
                "memo": line.memo,
                "debit_minor": line.debit_minor,
                "credit_minor": line.credit_minor,
            }
            for line in lines
        ],
    }



def reverse_journal_entry(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID,
    journal_entry_id: UUID,
    idempotency_key: str,
) -> tuple[JournalEntry, bool]:
    original = db.scalar(
        select(JournalEntry)
        .where(
            JournalEntry.id == journal_entry_id,
            JournalEntry.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if original is None:
        raise ValueError("Journal entry not found")
    original_lines = db.scalars(
        select(JournalLine)
        .where(
            JournalLine.tenant_id == tenant_id,
            JournalLine.journal_entry_id == original.id,
        )
        .order_by(JournalLine.line_number)
    ).all()
    if len(original_lines) < 2:
        raise ValueError("Journal entry has no valid posted lines")
    reversal_lines = [
        {
            "account_code": line.account_code,
            "memo": f"Reversal: {line.memo}" if line.memo else "Reversal",
            "debit_minor": line.credit_minor,
            "credit_minor": line.debit_minor,
        }
        for line in original_lines
    ]
    return create_journal_entry(
        db,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
        currency=original.currency,
        description=f"Reversal of {original.id}: {original.description}"[:500],
        lines=reversal_lines,
        reversal_of_id=original.id,
    )
