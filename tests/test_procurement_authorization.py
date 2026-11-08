import pytest

from retail_app.security.authorization import (
    AccessContext,
    AccessDenied,
    Permission,
    ResourceScope,
    Role,
    authorize,
)


def test_branch_manager_can_create_purchase_order_in_assigned_branch():
    actor = AccessContext("manager", "tenant-a", Role.BRANCH_MANAGER, frozenset({"branch-a"}))
    authorize(actor, Permission.PURCHASE_ORDER_CREATE, ResourceScope("tenant-a", "branch-a"))


def test_branch_manager_cannot_create_purchase_order_in_other_branch():
    actor = AccessContext("manager", "tenant-a", Role.BRANCH_MANAGER, frozenset({"branch-a"}))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.PURCHASE_ORDER_CREATE, ResourceScope("tenant-a", "branch-b"))


def test_branch_manager_cannot_approve_purchase_order():
    actor = AccessContext("manager", "tenant-a", Role.BRANCH_MANAGER, frozenset({"branch-a"}))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.PURCHASE_ORDER_APPROVE, ResourceScope("tenant-a", "branch-a"))


def test_owner_admin_can_approve_within_own_tenant():
    actor = AccessContext("owner", "tenant-a", Role.OWNER_ADMIN)
    authorize(actor, Permission.PURCHASE_ORDER_APPROVE, ResourceScope("tenant-a", "branch-a"))


def test_supplier_permission_is_not_granted_to_employee():
    actor = AccessContext("employee", "tenant-a", Role.EMPLOYEE, frozenset({"branch-a"}))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.SUPPLIER_WRITE, ResourceScope("tenant-a", "branch-a"))
