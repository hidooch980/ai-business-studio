import pytest

from retail_app.security.authorization import (
    AccessContext,
    AccessDenied,
    Permission,
    ResourceScope,
    Role,
    authorize,
)


def test_employee_can_create_sale_only_in_assigned_branch():
    actor = AccessContext("staff-1", "tenant-1", Role.EMPLOYEE, frozenset({"branch-a"}))
    authorize(actor, Permission.SALES_CREATE, ResourceScope("tenant-1", "branch-a"))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.SALES_CREATE, ResourceScope("tenant-1", "branch-b"))


def test_manager_cannot_read_business_wide_overview():
    actor = AccessContext("manager-1", "tenant-1", Role.BRANCH_MANAGER, frozenset({"branch-a"}))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.BUSINESS_OVERVIEW_READ, ResourceScope("tenant-1", "branch-a"))


def test_customer_can_read_only_own_customer_resources():
    actor = AccessContext("customer-1", "tenant-1", Role.CUSTOMER)
    authorize(actor, Permission.LOYALTY_SELF_READ, ResourceScope("tenant-1", owner_id="customer-1"))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.LOYALTY_SELF_READ, ResourceScope("tenant-1", owner_id="customer-2"))


def test_cross_tenant_access_is_denied_even_for_owner():
    actor = AccessContext("owner-1", "tenant-1", Role.OWNER_ADMIN)
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.BUSINESS_OVERVIEW_READ, ResourceScope("tenant-2"))


def test_inactive_identity_is_denied():
    actor = AccessContext("staff-1", "tenant-1", Role.OWNER_ADMIN, active=False)
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.BUSINESS_OVERVIEW_READ, ResourceScope("tenant-1"))


def test_employee_cannot_grant_itself_owner_permission():
    actor = AccessContext("staff-1", "tenant-1", Role.EMPLOYEE, frozenset({"branch-a"}))
    with pytest.raises(AccessDenied):
        authorize(actor, Permission.BUSINESS_OVERVIEW_READ, ResourceScope("tenant-1", "branch-a"))
