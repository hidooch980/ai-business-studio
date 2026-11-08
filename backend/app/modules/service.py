"""Tenant-scoped subscription provisioning and module entitlement rules."""
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.identity.models import TenantModuleEntitlement, TenantSubscription
from backend.app.modules.registry import MODULES, Edition, ModuleStatus, resolve_edition


def provision_tenant_modules(
    db: Session,
    *,
    tenant_id: UUID,
    actor_user_id: UUID | None,
    edition: Edition = Edition.STARTER,
) -> TenantSubscription:
    """Create the initial edition and its module entitlements for a new tenant."""
    resolved = resolve_edition(edition)
    selected = {
        item["module_id"]
        for item in resolved["modules"]
        if item["included_by_edition_or_addon"]
    }
    subscription = TenantSubscription(
        tenant_id=tenant_id,
        edition=edition.value,
        status="active",
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(subscription)
    for module in MODULES:
        entitled = module.module_id in selected
        dependencies_ready = all(
            dependency in selected
            and next(item for item in MODULES if item.module_id == dependency).status
            is not ModuleStatus.PLANNED
            for dependency in module.dependencies
        )
        db.add(
            TenantModuleEntitlement(
                tenant_id=tenant_id,
                module_id=module.module_id,
                source="edition",
                is_entitled=entitled,
                is_enabled=(
                    entitled
                    and dependencies_ready
                    and module.status is not ModuleStatus.PLANNED
                ),
                updated_by_user_id=actor_user_id,
            )
        )
    return subscription
