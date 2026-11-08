"""Transactional procurement-to-payment services.

All writes share the caller's tenant transaction, immutable audit/event records and
tenant-scoped idempotency. Amounts are integer minor currency units.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import uuid4

from retail_app.infrastructure.audit import record_audit
from retail_app.infrastructure.events import append_domain_event
from retail_app.infrastructure.idempotency import complete_idempotency, reserve_idempotency
from retail_app.security.authorization import (
    AccessContext,
    Permission,
    ResourceScope,
    Role,
    authorize,
)


def _version(connection: Any, tenant_id: str, aggregate_type: str, aggregate_id: str) -> int:
    row = connection.execute(
        """SELECT COALESCE(MAX(aggregate_version), 0) + 1
           FROM domain_events
           WHERE tenant_id = %s AND aggregate_type = %s AND aggregate_id = %s""",
        (tenant_id, aggregate_type, aggregate_id),
    ).fetchone()
    return int(row[0])


def _event(connection: Any, context: AccessContext, aggregate_type: str,
           aggregate_id: str, event_type: str, payload: dict[str, object]) -> None:
    append_domain_event(
        connection, tenant_id=context.tenant_id, aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=_version(connection, context.tenant_id, aggregate_type, aggregate_id),
        event_type=event_type, payload=payload, destination="internal",
    )


def _audit(connection: Any, context: AccessContext, action: str, resource_type: str,
           resource_id: str, request_id: str | None, details: dict[str, object] | None = None) -> None:
    record_audit(
        connection, tenant_id=context.tenant_id, actor_identity_id=context.subject_id,
        action=action, resource_type=resource_type, resource_id=resource_id,
        outcome="success", request_id=request_id, details=details or {},
    )


def get_purchase_order(database: Any, context: AccessContext, order_id: str) -> dict[str, object]:
    """Read one purchase order and its lines within the caller's tenant/branch scope."""
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        row = conn.execute(
            """SELECT id, branch_id, supplier_id, order_number, currency, status,
                      order_date, expected_date, notes
               FROM purchase_orders WHERE tenant_id = %s AND id = %s""",
            (context.tenant_id, order_id),
        ).fetchone()
        if row is None:
            raise LookupError("purchase order not found")
        authorize(context, Permission.PURCHASE_ORDER_READ,
                  ResourceScope(context.tenant_id, branch_id=str(row[1])))
        lines = conn.execute(
            """SELECT line_number, item_id, description, quantity_milli, unit_price_minor
               FROM purchase_order_lines
               WHERE tenant_id = %s AND purchase_order_id = %s ORDER BY line_number""",
            (context.tenant_id, order_id),
        ).fetchall()
        return {
            "id": str(row[0]), "branch_id": str(row[1]), "supplier_id": str(row[2]),
            "order_number": row[3], "currency": row[4].strip(), "status": row[5],
            "order_date": row[6].isoformat(),
            "expected_date": row[7].isoformat() if row[7] else None, "notes": row[8],
            "lines": [
                {"line_number": x[0], "item_id": str(x[1]), "description": x[2],
                 "quantity_milli": x[3], "unit_price_minor": x[4]}
                for x in lines
            ],
        }


def list_purchase_orders(database: Any, context: AccessContext, *, branch_id: str | None = None,
                         status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, object]]:
    """List purchase orders with bounded pagination and enforced branch scope."""
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("limit must be 1..200 and offset must be non-negative")
    if context.role in {Role.BRANCH_MANAGER, Role.EMPLOYEE}:
        if branch_id is not None and branch_id not in context.branch_ids:
            raise PermissionError("branch scope denied")
        branch_ids = sorted(context.branch_ids)
        if not branch_ids:
            return []
    else:
        branch_ids = [branch_id] if branch_id else []
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        if branch_ids:
            rows = conn.execute(
                """SELECT id, branch_id, supplier_id, order_number, currency, status, order_date
                   FROM purchase_orders WHERE tenant_id = %s
                   AND branch_id = ANY(%s::uuid[]) AND (%s::text IS NULL OR status = %s::text)
                   ORDER BY order_date DESC, order_number LIMIT %s OFFSET %s""",
                (context.tenant_id, branch_ids, status, status, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, branch_id, supplier_id, order_number, currency, status, order_date
                   FROM purchase_orders WHERE tenant_id = %s
                   AND (%s::text IS NULL OR status = %s::text)
                   ORDER BY order_date DESC, order_number LIMIT %s OFFSET %s""",
                (context.tenant_id, status, status, limit, offset),
            ).fetchall()
        results = []
        for row in rows:
            authorize(context, Permission.PURCHASE_ORDER_READ,
                      ResourceScope(context.tenant_id, branch_id=str(row[1])))
            results.append({
                "id": str(row[0]), "branch_id": str(row[1]), "supplier_id": str(row[2]),
                "order_number": row[3], "currency": row[4].strip(), "status": row[5],
                "order_date": row[6].isoformat(),
            })
        return results


def update_draft_purchase_order(database: Any, context: AccessContext, order_id: str, *,
                                supplier_id: str, currency: str, order_date: date,
                                lines: list[dict[str, object]], idempotency_key: str,
                                request_id: str | None = None) -> dict[str, object]:
    """Replace editable PO fields/lines; approved orders are immutable."""
    payload = {"order_id": order_id, "supplier_id": supplier_id, "currency": currency,
               "order_date": order_date.isoformat(), "lines": lines}
    operation = "procurement.purchase_order.update"
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        cached = reserve_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                                     key=idempotency_key, payload=payload)
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]
        po = conn.execute(
            """SELECT branch_id, status FROM purchase_orders
               WHERE tenant_id = %s AND id = %s FOR UPDATE""",
            (context.tenant_id, order_id),
        ).fetchone()
        if po is None:
            raise LookupError("purchase order not found")
        authorize(context, Permission.PURCHASE_ORDER_CREATE,
                  ResourceScope(context.tenant_id, branch_id=str(po[0])))
        if po[1] != "draft":
            raise ValueError("only draft purchase orders can be edited")
        if len(currency) != 3 or not currency.isalpha() or not currency.isupper():
            raise ValueError("currency must be a three-letter uppercase code")
        if not lines:
            raise ValueError("purchase order requires at least one line")
        supplier = conn.execute(
            "SELECT status FROM suppliers WHERE tenant_id = %s AND id = %s FOR SHARE",
            (context.tenant_id, supplier_id),
        ).fetchone()
        if supplier is None or supplier[0] != "active":
            raise ValueError("supplier must exist and be active")
        conn.execute(
            """UPDATE purchase_orders SET supplier_id = %s, currency = %s,
               order_date = %s, updated_at = now() WHERE tenant_id = %s AND id = %s""",
            (supplier_id, currency, order_date, context.tenant_id, order_id),
        )
        conn.execute(
            "DELETE FROM purchase_order_lines WHERE tenant_id = %s AND purchase_order_id = %s",
            (context.tenant_id, order_id),
        )
        total = 0
        for line in lines:
            qty, price, number = int(line["quantity_milli"]), int(line["unit_price_minor"]), int(line["line_number"])
            numerator = qty * price
            if qty <= 0 or price < 0 or numerator % 1000:
                raise ValueError("invalid quantity, price or fractional minor-unit line total")
            total += numerator // 1000
            conn.execute(
                """INSERT INTO purchase_order_lines
                   (tenant_id, purchase_order_id, line_number, item_id, description,
                    quantity_milli, unit_price_minor)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (context.tenant_id, order_id, number, str(line["item_id"]),
                 str(line["description"]), qty, price),
            )
        response = {"id": order_id, "status": "draft", "total_minor": total}
        _audit(conn, context, "purchase_order.update", "purchase_order", order_id, request_id,
               {"line_count": len(lines)})
        _event(conn, context, "purchase_order", order_id, "purchase_order.updated", response)
        complete_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                             key=idempotency_key, status=200, body=response)
        return response


def approve_purchase_order(database: Any, context: AccessContext, order_id: str, *,
                           idempotency_key: str, request_id: str | None = None) -> dict[str, object]:
    """Approve a draft PO; approval is restricted to tenant owner/admin."""
    authorize(context, Permission.PURCHASE_ORDER_APPROVE, ResourceScope(context.tenant_id))
    payload = {"order_id": order_id}
    operation = "procurement.purchase_order.approve"
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        cached = reserve_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                                     key=idempotency_key, payload=payload)
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]
        row = conn.execute(
            """SELECT status FROM purchase_orders
               WHERE tenant_id = %s AND id = %s FOR UPDATE""",
            (context.tenant_id, order_id),
        ).fetchone()
        if row is None:
            raise LookupError("purchase order not found")
        if row[0] != "draft":
            raise ValueError("only draft purchase orders can be approved")
        conn.execute(
            """UPDATE purchase_orders SET status = 'approved', approved_by = %s,
               approved_at = now(), updated_at = now()
               WHERE tenant_id = %s AND id = %s""",
            (context.subject_id, context.tenant_id, order_id),
        )
        response = {"id": order_id, "status": "approved"}
        _audit(conn, context, "purchase_order.approve", "purchase_order", order_id, request_id)
        _event(conn, context, "purchase_order", order_id, "purchase_order.approved", response)
        complete_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                             key=idempotency_key, status=200, body=response)
        return response


def _post_journal(conn: Any, *, tenant_id: str, source_type: str, source_id: str,
                  currency: str, debit_account: str, credit_account: str, amount_minor: int) -> None:
    if amount_minor <= 0:
        return
    journal_id = str(uuid4())
    for account, debit, credit in (
        (debit_account, amount_minor, 0), (credit_account, 0, amount_minor)
    ):
        conn.execute(
            """INSERT INTO financial_ledger_entries
               (tenant_id, id, journal_id, source_type, source_id, account_code,
                currency, debit_minor, credit_minor)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (tenant_id, str(uuid4()), journal_id, source_type, source_id, account,
             currency, debit, credit),
        )


def receive_goods(database: Any, context: AccessContext, order_id: str, *,
                  receipt_number: str, received_at: datetime,
                  lines: list[dict[str, object]], idempotency_key: str,
                  allow_overdelivery: bool = False, request_id: str | None = None) -> dict[str, object]:
    """Post a receipt with explicit shortage/overdelivery/damage discrepancy controls."""
    payload = {"order_id": order_id, "receipt_number": receipt_number,
               "received_at": received_at.isoformat(), "lines": lines,
               "allow_overdelivery": allow_overdelivery}
    operation = "procurement.goods_receipt.create"
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        cached = reserve_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                                     key=idempotency_key, payload=payload)
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]
        po = conn.execute(
            """SELECT branch_id, status, currency FROM purchase_orders
               WHERE tenant_id = %s AND id = %s FOR UPDATE""",
            (context.tenant_id, order_id),
        ).fetchone()
        if po is None:
            raise LookupError("purchase order not found")
        authorize(context, Permission.GOODS_RECEIPT_CREATE,
                  ResourceScope(context.tenant_id, branch_id=str(po[0])))
        if po[1] not in {"approved", "partially_received"}:
            raise ValueError("goods can only be received against an approved purchase order")
        if not lines:
            raise ValueError("receipt requires at least one line")
        receipt_id = str(uuid4())
        conn.execute(
            """INSERT INTO goods_receipts
               (tenant_id, id, branch_id, purchase_order_id, receipt_number, received_at, received_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (context.tenant_id, receipt_id, po[0], order_id, receipt_number,
             received_at, context.subject_id),
        )
        discrepancies: list[dict[str, object]] = []
        accepted_value = 0
        for line in lines:
            number = int(line["po_line_number"])
            received = int(line["received_quantity_milli"])
            accepted = int(line["accepted_quantity_milli"])
            rejected = int(line["rejected_quantity_milli"])
            code = line.get("discrepancy_code")
            if received <= 0 or accepted < 0 or rejected < 0 or received != accepted + rejected:
                raise ValueError("receipt quantities must be positive and received = accepted + rejected")
            po_line = conn.execute(
                """SELECT quantity_milli, unit_price_minor, item_id FROM purchase_order_lines
                   WHERE tenant_id = %s AND purchase_order_id = %s AND line_number = %s""",
                (context.tenant_id, order_id, number),
            ).fetchone()
            if po_line is None:
                raise ValueError("receipt references an unknown purchase-order line")
            prior = conn.execute(
                """SELECT COALESCE(SUM(grl.accepted_quantity_milli), 0)
                   FROM goods_receipt_lines grl
                   JOIN goods_receipts gr ON gr.tenant_id = grl.tenant_id AND gr.id = grl.goods_receipt_id
                   WHERE grl.tenant_id = %s AND grl.purchase_order_id = %s
                     AND grl.po_line_number = %s AND gr.status = 'posted'""",
                (context.tenant_id, order_id, number),
            ).fetchone()[0]
            over = int(prior) + received > int(po_line[0])
            if over and context.role is not Role.OWNER_ADMIN:
                raise PermissionError("overdelivery approval requires tenant owner/admin")
            if over and not allow_overdelivery:
                raise ValueError("overdelivery exceeds ordered quantity; explicit approval is required")
            if (received != accepted or over) and not code:
                raise ValueError("shortage, rejection or overdelivery requires a discrepancy code")
            if over and code != "overdelivery":
                raise ValueError("overdelivery requires the overdelivery discrepancy code")
            if code and code not in {"shortage", "overdelivery", "damaged", "wrong_item", "quality", "other"}:
                raise ValueError("unsupported discrepancy code")
            receipt_line_id = str(uuid4())
            conn.execute(
                """INSERT INTO goods_receipt_lines
                   (tenant_id, id, goods_receipt_id, purchase_order_id, po_line_number,
                    received_quantity_milli, accepted_quantity_milli, rejected_quantity_milli,
                    discrepancy_code, discrepancy_note)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (context.tenant_id, receipt_line_id, receipt_id, order_id, number,
                 received, accepted, rejected, code, line.get("discrepancy_note")),
            )
            if accepted > 0:
                conn.execute(
                    """INSERT INTO inventory_movements
                       (tenant_id, id, branch_id, item_id, movement_type, quantity_milli,
                        source_type, source_id, source_line_id, occurred_at, created_by)
                       VALUES (%s, %s, %s, %s, 'purchase_receipt', %s,
                               'goods_receipt', %s, %s, %s, %s)""",
                    (context.tenant_id, str(uuid4()), po[0], po_line[2], accepted,
                     receipt_id, receipt_line_id, received_at, context.subject_id),
                )
            numerator = accepted * int(po_line[1])
            if numerator % 1000:
                raise ValueError("accepted receipt value has fractional minor units")
            accepted_value += numerator // 1000
            if received != accepted or over:
                discrepancies.append({"po_line_number": number, "code": code,
                                      "received_quantity_milli": received,
                                      "accepted_quantity_milli": accepted,
                                      "ordered_quantity_milli": int(po_line[0])})
        # Derive PO state from cumulative accepted quantities across all posted receipts.
        totals = conn.execute(
            """SELECT pol.line_number, pol.quantity_milli,
                      COALESCE(SUM(grl.accepted_quantity_milli), 0)
               FROM purchase_order_lines pol
               LEFT JOIN goods_receipt_lines grl
                 ON grl.tenant_id = pol.tenant_id
                AND grl.purchase_order_id = pol.purchase_order_id
                AND grl.po_line_number = pol.line_number
               LEFT JOIN goods_receipts gr
                 ON gr.tenant_id = grl.tenant_id AND gr.id = grl.goods_receipt_id
                AND gr.status = 'posted'
               WHERE pol.tenant_id = %s AND pol.purchase_order_id = %s
               GROUP BY pol.line_number, pol.quantity_milli""",
            (context.tenant_id, order_id),
        ).fetchall()
        fully_received = all(int(x[2]) >= int(x[1]) for x in totals)
        any_received = any(int(x[2]) > 0 for x in totals)
        new_status = "received" if fully_received else ("partially_received" if any_received else "approved")
        conn.execute(
            "UPDATE purchase_orders SET status = %s, updated_at = now() WHERE tenant_id = %s AND id = %s",
            (new_status, context.tenant_id, order_id),
        )
        _post_journal(conn, tenant_id=context.tenant_id, source_type="goods_receipt",
                      source_id=receipt_id, currency=po[2].strip(), debit_account="INVENTORY",
                      credit_account="GRNI", amount_minor=accepted_value)
        response = {"id": receipt_id, "purchase_order_id": order_id,
                    "status": "posted", "purchase_order_status": new_status,
                    "discrepancies": discrepancies}
        _audit(conn, context, "goods_receipt.post", "goods_receipt", receipt_id, request_id,
               {"discrepancy_count": len(discrepancies)})
        _event(conn, context, "purchase_order", order_id, "goods_receipt.posted", response)
        complete_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                             key=idempotency_key, status=201, body=response)
        return response


def match_supplier_invoice(database: Any, context: AccessContext, *, invoice_id: str,
                           supplier_id: str, purchase_order_id: str, invoice_number: str,
                           currency: str, invoice_date: date, due_date: date,
                           invoice_total_minor: int, lines: list[dict[str, object]],
                           idempotency_key: str, request_id: str | None = None) -> dict[str, object]:
    """Perform PO/receipt/invoice three-way match; disputed invoices cannot create AP."""
    payload = {"invoice_id": invoice_id, "supplier_id": supplier_id,
               "purchase_order_id": purchase_order_id, "invoice_number": invoice_number,
               "currency": currency, "invoice_date": invoice_date.isoformat(),
               "due_date": due_date.isoformat(), "invoice_total_minor": invoice_total_minor,
               "lines": lines}
    operation = "procurement.supplier_invoice.match"
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        cached = reserve_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                                     key=idempotency_key, payload=payload)
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]
        po = conn.execute(
            """SELECT branch_id, supplier_id, currency FROM purchase_orders
               WHERE tenant_id = %s AND id = %s FOR UPDATE""",
            (context.tenant_id, purchase_order_id),
        ).fetchone()
        if po is None:
            raise LookupError("purchase order not found")
        authorize(context, Permission.SUPPLIER_INVOICE_WRITE,
                  ResourceScope(context.tenant_id, branch_id=str(po[0])))
        if str(po[1]) != supplier_id or po[2].strip() != currency:
            raise ValueError("invoice supplier/currency must match purchase order")
        if due_date < invoice_date or invoice_total_minor <= 0 or not lines:
            raise ValueError("invalid invoice dates, amount or empty lines")
        conn.execute(
            """INSERT INTO supplier_invoices
               (tenant_id, id, supplier_id, purchase_order_id, invoice_number, currency,
                invoice_date, due_date, invoice_total_minor, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (context.tenant_id, invoice_id, supplier_id, purchase_order_id, invoice_number,
             currency, invoice_date, due_date, invoice_total_minor, context.subject_id),
        )
        line_sum = 0
        mismatches: list[dict[str, object]] = []
        for line in lines:
            number = int(line["po_line_number"])
            receipt_line_id = str(line["goods_receipt_line_id"])
            qty, price = int(line["quantity_milli"]), int(line["unit_price_minor"])
            if qty <= 0 or price < 0 or qty * price % 1000:
                raise ValueError("invoice line quantity/price is invalid or not exactly representable")
            total = qty * price // 1000
            line_sum += total
            match = conn.execute(
                """SELECT pol.quantity_milli, pol.unit_price_minor,
                          grl.accepted_quantity_milli, gr.purchase_order_id
                   FROM purchase_order_lines pol
                   JOIN goods_receipt_lines grl
                     ON grl.tenant_id = pol.tenant_id AND grl.purchase_order_id = pol.purchase_order_id
                    AND grl.po_line_number = pol.line_number
                   JOIN goods_receipts gr
                     ON gr.tenant_id = grl.tenant_id AND gr.id = grl.goods_receipt_id
                   WHERE pol.tenant_id = %s AND pol.purchase_order_id = %s
                     AND pol.line_number = %s AND grl.id = %s AND gr.status = 'posted'""",
                (context.tenant_id, purchase_order_id, number, receipt_line_id),
            ).fetchone()
            if match is None:
                raise ValueError("invoice line must reference a receipt line from this purchase order")
            already_invoiced = conn.execute(
                """SELECT COALESCE(SUM(sil.quantity_milli), 0)
                   FROM supplier_invoice_lines sil
                   JOIN supplier_invoices si ON si.tenant_id = sil.tenant_id AND si.id = sil.invoice_id
                   WHERE sil.tenant_id = %s AND sil.goods_receipt_line_id = %s
                     AND si.status IN ('matched', 'disputed')""",
                (context.tenant_id, receipt_line_id),
            ).fetchone()[0]
            if qty + int(already_invoiced) > int(match[2]):
                mismatches.append({"po_line_number": number, "reason": "invoice_quantity_exceeds_accepted_receipt"})
            if price != int(match[1]):
                mismatches.append({"po_line_number": number, "reason": "unit_price_differs_from_purchase_order"})
            conn.execute(
                """INSERT INTO supplier_invoice_lines
                   (tenant_id, id, invoice_id, purchase_order_id, po_line_number,
                    goods_receipt_line_id, quantity_milli, unit_price_minor, line_total_minor)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (context.tenant_id, str(uuid4()), invoice_id, purchase_order_id, number,
                 receipt_line_id, qty, price, total),
            )
        if line_sum != invoice_total_minor:
            mismatches.append({"reason": "invoice_header_total_does_not_equal_line_sum",
                               "line_sum_minor": line_sum, "header_total_minor": invoice_total_minor})
        status = "disputed" if mismatches else "matched"
        conn.execute(
            """UPDATE supplier_invoices SET status = %s,
               matched_at = CASE WHEN %s = 'matched' THEN now() ELSE NULL END
               WHERE tenant_id = %s AND id = %s""",
            (status, status, context.tenant_id, invoice_id),
        )
        payable_id = None
        if status == "matched":
            payable_id = str(uuid4())
            conn.execute(
                """INSERT INTO accounts_payable
                   (tenant_id, id, invoice_id, supplier_id, currency, original_amount_minor,
                    outstanding_amount_minor, due_date)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (context.tenant_id, payable_id, invoice_id, supplier_id, currency,
                 invoice_total_minor, invoice_total_minor, due_date),
            )
            _post_journal(conn, tenant_id=context.tenant_id, source_type="supplier_invoice",
                          source_id=invoice_id, currency=currency, debit_account="GRNI",
                          credit_account="ACCOUNTS_PAYABLE", amount_minor=invoice_total_minor)
        response = {"id": invoice_id, "status": status, "payable_id": payable_id,
                    "mismatches": mismatches}
        _audit(conn, context, "supplier_invoice.match", "supplier_invoice", invoice_id,
               request_id, {"status": status, "mismatch_count": len(mismatches)})
        _event(conn, context, "supplier_invoice", invoice_id,
               "supplier_invoice.matched" if status == "matched" else "supplier_invoice.disputed",
               response)
        complete_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                             key=idempotency_key, status=201, body=response)
        return response


def record_supplier_payment(database: Any, context: AccessContext, *, payment_id: str,
                            supplier_id: str, payment_reference: str, currency: str,
                            amount_minor: int, paid_at: datetime, method: str,
                            allocations: list[dict[str, object]], idempotency_key: str,
                            request_id: str | None = None) -> dict[str, object]:
    """Record a payment and allocate it to open payables; duplicate references/keys are rejected."""
    payload = {"payment_id": payment_id, "supplier_id": supplier_id,
               "payment_reference": payment_reference, "currency": currency,
               "amount_minor": amount_minor, "paid_at": paid_at.isoformat(),
               "method": method, "allocations": allocations}
    operation = "procurement.supplier_payment.create"
    authorize(context, Permission.SUPPLIER_PAYMENT_WRITE, ResourceScope(context.tenant_id))
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        cached = reserve_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                                     key=idempotency_key, payload=payload)
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]
        if amount_minor <= 0 or not allocations:
            raise ValueError("payment amount and at least one payable allocation are required")
        if method not in {"bank_transfer", "cash", "card", "other"}:
            raise ValueError("unsupported payment method")
        supplier = conn.execute(
            "SELECT id FROM suppliers WHERE tenant_id = %s AND id = %s",
            (context.tenant_id, supplier_id),
        ).fetchone()
        if supplier is None:
            raise LookupError("supplier not found")
        conn.execute(
            """INSERT INTO supplier_payments
               (tenant_id, id, supplier_id, payment_reference, currency, amount_minor,
                paid_at, method, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (context.tenant_id, payment_id, supplier_id, payment_reference, currency,
             amount_minor, paid_at, method, context.subject_id),
        )
        allocated = 0
        payable_ids = []
        for allocation in allocations:
            payable_id, value = str(allocation["payable_id"]), int(allocation["amount_minor"])
            if value <= 0:
                raise ValueError("allocation amount must be positive")
            payable = conn.execute(
                """SELECT supplier_id, currency, outstanding_amount_minor
                   FROM accounts_payable WHERE tenant_id = %s AND id = %s FOR UPDATE""",
                (context.tenant_id, payable_id),
            ).fetchone()
            if payable is None:
                raise LookupError("accounts payable record not found")
            if str(payable[0]) != supplier_id or payable[1].strip() != currency:
                raise ValueError("payment supplier and currency must match payable")
            if value > int(payable[2]):
                raise ValueError("payment allocation exceeds outstanding payable")
            conn.execute(
                """INSERT INTO payment_allocations
                   (tenant_id, id, payment_id, payable_id, amount_minor)
                   VALUES (%s, %s, %s, %s, %s)""",
                (context.tenant_id, str(uuid4()), payment_id, payable_id, value),
            )
            remaining = int(payable[2]) - value
            conn.execute(
                """UPDATE accounts_payable SET outstanding_amount_minor = %s,
                   status = %s WHERE tenant_id = %s AND id = %s""",
                (remaining, "paid" if remaining == 0 else "partially_paid",
                 context.tenant_id, payable_id),
            )
            allocated += value
            payable_ids.append(payable_id)
        if allocated != amount_minor:
            raise ValueError("payment amount must equal the sum of its allocations")
        cash_account = {"bank_transfer": "BANK", "cash": "CASH",
                        "card": "CARD_CLEARING", "other": "PAYMENT_CLEARING"}[method]
        _post_journal(conn, tenant_id=context.tenant_id, source_type="supplier_payment",
                      source_id=payment_id, currency=currency,
                      debit_account="ACCOUNTS_PAYABLE", credit_account=cash_account,
                      amount_minor=amount_minor)
        response = {"id": payment_id, "status": "posted", "amount_minor": amount_minor,
                    "allocated_minor": allocated, "payable_ids": payable_ids}
        _audit(conn, context, "supplier_payment.post", "supplier_payment", payment_id,
               request_id, {"payment_reference": payment_reference, "method": method})
        _event(conn, context, "supplier_payment", payment_id, "supplier_payment.posted", response)
        complete_idempotency(conn, tenant_id=context.tenant_id, operation=operation,
                             key=idempotency_key, status=201, body=response)
        return response


def list_accounts_payable(database: Any, context: AccessContext, *,
                          supplier_id: str | None = None, due_before: date | None = None,
                          limit: int = 100) -> list[dict[str, object]]:
    """List open/part-paid payables and due dates within the authenticated tenant."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be 1..200")
    authorize(context, Permission.ACCOUNTS_PAYABLE_READ, ResourceScope(context.tenant_id))
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        rows = conn.execute(
            """SELECT id, invoice_id, supplier_id, currency, original_amount_minor,
                      outstanding_amount_minor, due_date, status
               FROM accounts_payable WHERE tenant_id = %s
                 AND (%s::uuid IS NULL OR supplier_id = %s::uuid)
                 AND (%s::date IS NULL OR due_date <= %s::date)
               ORDER BY due_date, id LIMIT %s""",
            (context.tenant_id, supplier_id, supplier_id, due_before, due_before, limit),
        ).fetchall()
        return [{"id": str(r[0]), "invoice_id": str(r[1]), "supplier_id": str(r[2]),
                 "currency": r[3].strip(), "original_amount_minor": r[4],
                 "outstanding_amount_minor": r[5], "due_date": r[6].isoformat(),
                 "status": r[7]} for r in rows]


def get_stock_balance(database: Any, context: AccessContext, *, branch_id: str,
                      item_id: str) -> dict[str, object]:
    """Derive on-hand quantity from the append-only inventory movement subledger."""
    authorize(context, Permission.INVENTORY_READ,
              ResourceScope(context.tenant_id, branch_id=branch_id))
    with database.tenant_transaction(tenant_id=context.tenant_id, subject_id=context.subject_id, expected_role=context.role.value, expected_branch_ids=context.branch_ids, session_id=context.session_id, session_token_hash=context.session_token_hash) as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(quantity_milli), 0)
               FROM inventory_movements
               WHERE tenant_id = %s AND branch_id = %s AND item_id = %s""",
            (context.tenant_id, branch_id, item_id),
        ).fetchone()
        return {"branch_id": branch_id, "item_id": item_id,
                "on_hand_quantity_milli": int(row[0])}
