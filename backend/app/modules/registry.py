"""Versioned module catalog and edition entitlement resolver.

This catalog describes product packaging only. It does not grant access by itself:
production authorization must combine tenant entitlements, module lifecycle,
feature flags, RBAC permissions, and server-side policy checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Mapping


class ModuleStatus(StrEnum):
    FOUNDATION = "foundation"
    PREVIEW = "preview"
    PLANNED = "planned"


class Edition(StrEnum):
    STARTER = "starter"
    GROWTH = "growth"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class ModuleDefinition:
    module_id: str
    name: str
    module_version: str
    status: ModuleStatus
    dependencies: tuple[str, ...] = ()
    addon: bool = False
    description: str = ""


@dataclass(frozen=True)
class EditionDefinition:
    edition: Edition
    name: str
    included_modules: tuple[str, ...]
    description: str


MODULES: tuple[ModuleDefinition, ...] = (
    ModuleDefinition("platform", "Core platform and identity", "1.0.0", ModuleStatus.FOUNDATION),
    ModuleDefinition("catalog", "Product and service catalog", "1.0.0", ModuleStatus.FOUNDATION, ("platform",)),
    ModuleDefinition("inventory", "Inventory and warehouses", "1.0.0", ModuleStatus.FOUNDATION, ("catalog",)),
    ModuleDefinition("finance", "Accounting and finance", "1.0.0", ModuleStatus.FOUNDATION, ("platform",)),
    ModuleDefinition("reports", "Operational reports", "1.0.0", ModuleStatus.PREVIEW, ("platform",)),
    ModuleDefinition("procurement", "Smart procurement", "0.1.0", ModuleStatus.PREVIEW, ("catalog", "inventory", "finance")),
    ModuleDefinition("sales", "Sales and order management", "0.1.0", ModuleStatus.PLANNED, ("catalog", "inventory", "finance")),
    ModuleDefinition("pos", "Smart point of sale", "0.1.0", ModuleStatus.PLANNED, ("sales", "inventory", "finance")),
    ModuleDefinition("crm", "Customer relationship management", "0.1.0", ModuleStatus.PLANNED, ("platform", "sales")),
    ModuleDefinition("workflows", "Approvals and workflow automation", "0.1.0", ModuleStatus.PREVIEW, ("platform",)),
    ModuleDefinition("treasury", "Cash, bank and treasury", "0.1.0", ModuleStatus.PLANNED, ("finance",)),
    ModuleDefinition("hr_payroll", "Human resources and payroll", "0.1.0", ModuleStatus.PLANNED, ("platform", "finance")),
    ModuleDefinition("analytics_ai", "AI analytics and business intelligence", "0.1.0", ModuleStatus.PLANNED, ("reports",)),
    ModuleDefinition("integrations", "External integrations and public APIs", "0.1.0", ModuleStatus.PLANNED, ("platform",)),
    ModuleDefinition("multi_company", "Multi-company and consolidation", "0.1.0", ModuleStatus.PLANNED, ("platform", "finance")),
    ModuleDefinition("manufacturing", "Manufacturing and MRP", "0.1.0", ModuleStatus.PLANNED, ("catalog", "inventory", "finance"), True),
    ModuleDefinition(
        "quality_assets", "Quality, maintenance and fixed assets", "0.1.0",
        ModuleStatus.PLANNED, ("inventory", "finance"), True,
    ),
    ModuleDefinition(
        "service_logistics", "Service desk, fleet and logistics", "0.1.0",
        ModuleStatus.PLANNED, ("platform", "inventory"), True,
    ),
    ModuleDefinition("portals", "Customer and supplier portals", "0.1.0", ModuleStatus.PLANNED, ("platform", "integrations"), True),
)

EDITIONS: tuple[EditionDefinition, ...] = (
    EditionDefinition(
        Edition.STARTER, "Starter",
        ("platform", "catalog", "inventory", "finance", "reports"),
        "Core operations for a single small business.",
    ),
    EditionDefinition(
        Edition.GROWTH, "Growth",
        ("platform", "catalog", "inventory", "finance", "reports", "procurement", "sales", "pos", "crm", "workflows"),
        "Connected sales, purchasing, POS and approval workflows.",
    ),
    EditionDefinition(
        Edition.BUSINESS, "Business",
        (
            "platform", "catalog", "inventory", "finance", "reports", "procurement",
            "sales", "pos", "crm", "workflows", "treasury", "hr_payroll", "analytics_ai",
        ),
        "Broader operational control, workforce and decision support.",
    ),
    EditionDefinition(
        Edition.ENTERPRISE, "Enterprise",
        tuple(module.module_id for module in MODULES if not module.addon),
        "Advanced multi-company, integration and governance capabilities.",
    ),
)

MODULE_BY_ID: Mapping[str, ModuleDefinition] = {module.module_id: module for module in MODULES}
EDITION_BY_ID: Mapping[Edition, EditionDefinition] = {edition.edition: edition for edition in EDITIONS}


def validate_catalog() -> None:
    """Fail fast on duplicate IDs, missing dependencies, cycles, or invalid versions."""
    import re

    if len(MODULE_BY_ID) != len(MODULES):
        raise ValueError("module IDs must be unique")
    if len(EDITION_BY_ID) != len(EDITIONS):
        raise ValueError("edition IDs must be unique")
    version_pattern = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    for module in MODULES:
        if not version_pattern.fullmatch(module.module_version):
            raise ValueError(f"invalid semantic version for module {module.module_id}")
        missing = set(module.dependencies) - set(MODULE_BY_ID)
        if missing:
            raise ValueError(f"unknown dependencies for {module.module_id}: {sorted(missing)}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module_id: str) -> None:
        if module_id in visiting:
            raise ValueError(f"module dependency cycle detected at {module_id}")
        if module_id in visited:
            return
        visiting.add(module_id)
        for dependency in MODULE_BY_ID[module_id].dependencies:
            visit(dependency)
        visiting.remove(module_id)
        visited.add(module_id)

    for module_id in MODULE_BY_ID:
        visit(module_id)
    for edition in EDITIONS:
        missing = set(edition.included_modules) - set(MODULE_BY_ID)
        if missing:
            raise ValueError(f"unknown modules in edition {edition.edition}: {sorted(missing)}")


def resolve_edition(edition: Edition | str, addons: tuple[str, ...] = ()) -> dict[str, object]:
    """Resolve an edition into an explainable module entitlement preview."""
    try:
        selected_edition = edition if isinstance(edition, Edition) else Edition(edition)
    except ValueError as exc:
        raise ValueError("unknown product edition") from exc

    definition = EDITION_BY_ID[selected_edition]
    selected = set(definition.included_modules)
    for addon in addons:
        module = MODULE_BY_ID.get(addon)
        if module is None or not module.addon:
            raise ValueError(f"unknown add-on module: {addon}")
        selected.add(addon)

    # Dependencies are included in the resolved set but not silently licensed.
    expanded = set(selected)
    pending = list(selected)
    while pending:
        current = pending.pop()
        for dependency in MODULE_BY_ID[current].dependencies:
            if dependency not in expanded:
                expanded.add(dependency)
                pending.append(dependency)

    modules = []
    for module_id in sorted(expanded):
        module = MODULE_BY_ID[module_id]
        required_entitlements: set[str] = set()
        dependency_queue = list(module.dependencies)
        while dependency_queue:
            dependency_id = dependency_queue.pop()
            if dependency_id in required_entitlements:
                continue
            required_entitlements.add(dependency_id)
            dependency_queue.extend(MODULE_BY_ID[dependency_id].dependencies)
        missing_entitlements = sorted(required_entitlements - selected)
        entitlement_included = module_id in selected
        dependencies_satisfied = not missing_entitlements
        modules.append({
            "module_id": module.module_id,
            "name": module.name,
            "module_version": module.module_version,
            "status": module.status.value,
            "included_by_edition_or_addon": entitlement_included,
            "dependencies": list(module.dependencies),
            "missing_dependency_entitlements": missing_entitlements,
            "dependencies_satisfied": dependencies_satisfied,
            "implementation_ready": module.status is ModuleStatus.FOUNDATION,
            "can_activate": entitlement_included and dependencies_satisfied and module.status is ModuleStatus.FOUNDATION,
            "preview_only": entitlement_included and dependencies_satisfied and module.status is ModuleStatus.PREVIEW,
            "requires_future_release": module.status is ModuleStatus.PLANNED,
        })
    return {
        "edition": selected_edition.value,
        "edition_name": definition.name,
        "modules": modules,
        "notice": "Catalog metadata is not an authorization grant. Enforce persisted tenant entitlements, feature flags and RBAC on every server-side operation.",
    }


validate_catalog()
