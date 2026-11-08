"""Transactional supplier and purchase-order application services."""
from __future__ import annotations

from typing import Any

from retail_app.infrastructure.audit import record_audit
from retail_app.infrastructure.events import append_domain_event
from retail_app.infrastructure.idempotency import (
    complete_idempotency,
    reserve_idempotency,
)
from retail_app.procurement.purchase_orders import PurchaseOrder, PurchaseOrderStatus
from retail_app.procurement.suppliers import Supplier, SupplierStatus
from retail_app.security.authorization import (
    AccessContext,
    Permission,
    ResourceScope,
    authorize,
)


def create_supplier(
    database: Any,
    context: AccessContext,
    supplier: Supplier,
    *,
    idempotency_key: str,
    request_id: str | None = None,
) -> dict[str, object]:
    """Create a tenant-wide supplier; only tenant administrators may write it."""
    if supplier.tenant_id != context.tenant_id:
        raise PermissionError("supplier tenant does not match authenticated tenant")
    if supplier.status is not SupplierStatus.ACTIVE:
        raise ValueError("new suppliers must start active")
    authorize(context, Permission.SUPPLIER_WRITE, ResourceScope(context.tenant_id))

    payload = {
        "id": supplier.id,
        "tenant_id": supplier.tenant_id,
        "legal_name": supplier.legal_name,
        "tax_identifier": supplier.tax_identifier,
        "phone": supplier.phone,
        "email": supplier.email,
        "address": supplier.address,
    }
    operation = "procurement.supplier.create"
    with database.tenant_transaction(
        tenant_id=context.tenant_id, subject_id=context.subject_id,
        expected_role=context.role.value, expected_branch_ids=context.branch_ids,
        session_id=context.session_id, session_token_hash=context.session_token_hash,
    ) as connection:
        cached = reserve_idempotency(
            connection, tenant_id=context.tenant_id, operation=operation,
            key=idempotency_key, payload=payload,
        )
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]

        connection.execute(
            """
            INSERT INTO suppliers
                (tenant_id, id, legal_name, status, tax_identifier, phone, email, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                context.tenant_id, supplier.id, supplier.legal_name, supplier.status.value,
                supplier.tax_identifier, supplier.phone, supplier.email, supplier.address,
            ),
        )
        response: dict[str, object] = {
            "id": supplier.id,
            "tenant_id": supplier.tenant_id,
            "legal_name": supplier.legal_name,
            "status": supplier.status.value,
        }
        record_audit(
            connection, tenant_id=context.tenant_id,
            actor_identity_id=context.subject_id, action="supplier.create",
            resource_type="supplier", resource_id=supplier.id, outcome="success",
            request_id=request_id, details={"status": supplier.status.value},
        )
        append_domain_event(
            connection, tenant_id=context.tenant_id, aggregate_type="supplier",
            aggregate_id=supplier.id, aggregate_version=1,
            event_type="supplier.created",
            payload={"id": supplier.id, "legal_name": supplier.legal_name,
                     "status": supplier.status.value},
            destination="internal",
        )
        complete_idempotency(
            connection, tenant_id=context.tenant_id, operation=operation,
            key=idempotency_key, status=201, body=response,
        )
        return response


def create_purchase_order(
    database: Any,
    context: AccessContext,
    order: PurchaseOrder,
    *,
    idempotency_key: str,
    request_id: str | None = None,
) -> dict[str, object]:
    """Create a draft PO after checking tenant, branch and active supplier scope."""
    if order.tenant_id != context.tenant_id:
        raise PermissionError("purchase order tenant does not match authenticated tenant")
    if order.status is not PurchaseOrderStatus.DRAFT:
        raise ValueError("purchase orders must be created as drafts")
    authorize(
        context, Permission.PURCHASE_ORDER_CREATE,
        ResourceScope(context.tenant_id, branch_id=order.branch_id),
    )

    payload = {
        "id": order.id,
        "tenant_id": order.tenant_id,
        "branch_id": order.branch_id,
        "supplier_id": order.supplier_id,
        "order_number": order.order_number,
        "currency": order.currency,
        "order_date": order.order_date.isoformat(),
        "lines": [
            {
                "line_number": line.line_number,
                "item_id": line.item_id,
                "description": line.description,
                "quantity_milli": line.quantity_milli,
                "unit_price_minor": line.unit_price_minor,
            }
            for line in order.lines
        ],
    }
    operation = "procurement.purchase_order.create"
    with database.tenant_transaction(
        tenant_id=context.tenant_id, subject_id=context.subject_id,
        expected_role=context.role.value, expected_branch_ids=context.branch_ids,
        session_id=context.session_id, session_token_hash=context.session_token_hash,
    ) as connection:
        cached = reserve_idempotency(
            connection, tenant_id=context.tenant_id, operation=operation,
            key=idempotency_key, payload=payload,
        )
        if cached is not None:
            return cached["body"]  # type: ignore[return-value]

        supplier = connection.execute(
            """
            SELECT status FROM suppliers
            WHERE tenant_id = %s AND id = %s
            FOR SHARE
            """,
            (context.tenant_id, order.supplier_id),
        ).fetchone()
        if supplier is None:
            raise ValueError("supplier does not exist in this tenant")
        if supplier[0] != SupplierStatus.ACTIVE.value:
            raise ValueError("purchase orders require an active supplier")

        connection.execute(
            """
            INSERT INTO purchase_orders
                (tenant_id, id, branch_id, supplier_id, order_number,
                 currency, status, order_date, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, 'draft', %s, %s)
            """,
            (
                context.tenant_id, order.id, order.branch_id, order.supplier_id,
                order.order_number, order.currency, order.order_date, context.subject_id,
            ),
        )
        for line in order.lines:
            connection.execute(
                """
                INSERT INTO purchase_order_lines
                    (tenant_id, purchase_order_id, line_number, item_id,
                     description, quantity_milli, unit_price_minor)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    context.tenant_id, order.id, line.line_number, line.item_id,
                    line.description, line.quantity_milli, line.unit_price_minor,
                ),
            )

        response: dict[str, object] = {
            "id": order.id,
            "tenant_id": order.tenant_id,
            "branch_id": order.branch_id,
            "supplier_id": order.supplier_id,
            "order_number": order.order_number,
            "currency": order.currency,
            "status": PurchaseOrderStatus.DRAFT.value,
            "total_minor": order.total_minor,
        }
        record_audit(
            connection, tenant_id=context.tenant_id,
            actor_identity_id=context.subject_id, action="purchase_order.create",
            resource_type="purchase_order", resource_id=order.id, outcome="success",
            request_id=request_id,
            details={"order_number": order.order_number, "line_count": len(order.lines)},
        )
        append_domain_event(
            connection, tenant_id=context.tenant_id, aggregate_type="purchase_order",
            aggregate_id=order.id, aggregate_version=1,
            event_type="purchase_order.created",
            payload={
                "id": order.id, "supplier_id": order.supplier_id,
                "branch_id": order.branch_id, "order_number": order.order_number,
                "currency": order.currency, "total_minor": order.total_minor,
            },
            destination="internal",
        )
        complete_idempotency(
            connection, tenant_id=context.tenant_id, operation=operation,
            key=idempotency_key, status=201, body=response,
        )
        return response
