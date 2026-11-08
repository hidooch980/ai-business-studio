"""Deny-by-default authorization primitives for retail service boundaries.

The caller must build AccessContext from trusted server-side identity and membership
records. Never construct it from request-body role, tenant, or branch claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    OWNER_ADMIN = "owner_admin"
    BRANCH_MANAGER = "branch_manager"
    EMPLOYEE = "employee"
    CUSTOMER = "customer"


class Permission(StrEnum):
    BUSINESS_OVERVIEW_READ = "business.overview.read"
    BRANCH_OVERVIEW_READ = "branch.overview.read"
    SALES_CREATE = "sales.create"
    INVENTORY_READ = "inventory.read"
    PURCHASE_REQUEST_CREATE = "purchase_request.create"
    SUPPLIER_READ = "supplier.read"
    SUPPLIER_WRITE = "supplier.write"
    PURCHASE_ORDER_CREATE = "purchase_order.create"
    PURCHASE_ORDER_READ = "purchase_order.read"
    PURCHASE_ORDER_APPROVE = "purchase_order.approve"
    GOODS_RECEIPT_CREATE = "goods_receipt.create"
    SUPPLIER_INVOICE_WRITE = "supplier_invoice.write"
    ACCOUNTS_PAYABLE_READ = "accounts_payable.read"
    SUPPLIER_PAYMENT_WRITE = "supplier_payment.write"
    CASH_SHIFT_OPERATE = "cash_shift.operate"
    CUSTOMER_SUPPORT_READ = "customer.support.read"
    CUSTOMER_SELF_READ = "customer.self.read"
    CUSTOMER_SELF_UPDATE = "customer.self.update"
    LOYALTY_SELF_READ = "loyalty.self.read"
    RECEIPT_SELF_READ = "receipt.self.read"


class AccessDenied(PermissionError):
    """Raised when an identity is inactive or outside its authorized scope."""


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Trusted identity and memberships resolved by the authentication layer."""

    subject_id: str
    tenant_id: str
    role: Role
    branch_ids: frozenset[str] = frozenset()
    active: bool = True
    session_id: str | None = None
    session_token_hash: bytes | None = None


@dataclass(frozen=True, slots=True)
class ResourceScope:
    """Tenant and optional branch/owner boundaries for the target resource."""

    tenant_id: str
    branch_id: str | None = None
    owner_id: str | None = None


_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER_ADMIN: frozenset(Permission),
    Role.BRANCH_MANAGER: frozenset(
        {
            Permission.BRANCH_OVERVIEW_READ,
            Permission.SALES_CREATE,
            Permission.INVENTORY_READ,
            Permission.PURCHASE_REQUEST_CREATE,
            Permission.SUPPLIER_READ,
            Permission.PURCHASE_ORDER_CREATE,
            Permission.PURCHASE_ORDER_READ,
            Permission.GOODS_RECEIPT_CREATE,
            Permission.CASH_SHIFT_OPERATE,
            Permission.CUSTOMER_SUPPORT_READ,
        }
    ),
    Role.EMPLOYEE: frozenset(
        {
            Permission.SALES_CREATE,
            Permission.INVENTORY_READ,
            Permission.CASH_SHIFT_OPERATE,
        }
    ),
    Role.CUSTOMER: frozenset(
        {
            Permission.CUSTOMER_SELF_READ,
            Permission.CUSTOMER_SELF_UPDATE,
            Permission.LOYALTY_SELF_READ,
            Permission.RECEIPT_SELF_READ,
        }
    ),
}


def authorize(
    context: AccessContext,
    permission: Permission,
    resource: ResourceScope,
) -> None:
    """Authorize one action against tenant, role, branch, and ownership scope.

    Returns None when allowed; raises AccessDenied otherwise. A missing or
    mismatched scope is always denied. This is a policy primitive, not an
    authentication/session implementation or a substitute for DB row scoping.
    """
    if not context.active:
        raise AccessDenied("inactive identity")
    if not context.subject_id or not context.tenant_id:
        raise AccessDenied("incomplete identity")
    # Fail closed if a context is forged or constructed with an unrecognized role.
    # This prevents a KeyError/500 from escaping the authorization boundary.
    if not isinstance(context.role, Role):
        raise AccessDenied("unsupported identity role")
    if context.tenant_id != resource.tenant_id:
        raise AccessDenied("cross-tenant access denied")
    if permission not in _ROLE_PERMISSIONS[context.role]:
        raise AccessDenied("permission denied")

    if context.role in {Role.BRANCH_MANAGER, Role.EMPLOYEE}:
        if resource.branch_id is None or resource.branch_id not in context.branch_ids:
            raise AccessDenied("branch scope denied")
    elif context.role is Role.CUSTOMER and (
        resource.owner_id is None or resource.owner_id != context.subject_id
    ):
        raise AccessDenied("customer ownership scope denied")
