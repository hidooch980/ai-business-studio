import pytest

from retail_app.security.authorization import (
    AccessContext,
    AccessDenied,
    Permission,
    ResourceScope,
    Role,
    authorize,
)


def test_branch_manager_can_receive_goods_only_in_assigned_branch():
    actor = AccessContext("manager", "tenant-a", Role.BRANCH_MANAGER, frozenset({"branch-a"}))
    authorize(actor, Permission.GOODS_RECEIPT_CREATE, ResourceScope("tenant-a", "branch-a"))


@pytest.mark.parametrize(
    "permission",
    [
        Permission.SUPPLIER_INVOICE_WRITE,
        Permission.ACCOUNTS_PAYABLE_READ,
        Permission.SUPPLIER_PAYMENT_WRITE,
    ],
)
def test_branch_manager_cannot_match_invoice_read_payables_or_post_payment(permission):
    actor = AccessContext("manager", "tenant-a", Role.BRANCH_MANAGER, frozenset({"branch-a"}))
    with pytest.raises(AccessDenied):
        authorize(actor, permission, ResourceScope("tenant-a", "branch-a"))


def test_owner_admin_can_manage_invoice_payable_and_supplier_payment():
    actor = AccessContext("owner", "tenant-a", Role.OWNER_ADMIN)
    for permission in (
        Permission.SUPPLIER_INVOICE_WRITE,
        Permission.ACCOUNTS_PAYABLE_READ,
        Permission.SUPPLIER_PAYMENT_WRITE,
    ):
        authorize(actor, permission, ResourceScope("tenant-a"))
