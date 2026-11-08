import pytest

from backend.app.modules.registry import (
    EDITIONS,
    MODULES,
    Edition,
    ModuleStatus,
    resolve_edition,
    validate_catalog,
)


def _by_id(result):
    return {item["module_id"]: item for item in result["modules"]}


def test_module_catalog_has_unique_ids_and_valid_dependencies():
    validate_catalog()
    assert len({module.module_id for module in MODULES}) == len(MODULES)


@pytest.mark.parametrize("edition", [item.edition for item in EDITIONS])
def test_every_edition_resolves_without_unknown_modules(edition):
    result = resolve_edition(edition)
    assert result["edition"] == edition.value
    assert result["modules"]


def test_growth_includes_sales_and_procurement_but_does_not_claim_them_ready():
    modules = _by_id(resolve_edition(Edition.GROWTH))
    assert modules["sales"]["included_by_edition_or_addon"] is True
    assert modules["procurement"]["preview_only"] is True
    assert modules["sales"]["requires_future_release"] is True
    assert modules["sales"]["can_activate"] is False


def test_addon_includes_its_dependencies_without_licensing_them_as_addons():
    modules = _by_id(resolve_edition(Edition.STARTER, ("manufacturing",)))
    assert modules["manufacturing"]["included_by_edition_or_addon"] is True
    assert modules["inventory"]["included_by_edition_or_addon"] is True
    assert modules["inventory"]["module_id"] in modules["manufacturing"]["dependencies"]


def test_non_addon_cannot_be_added_as_paid_addon():
    with pytest.raises(ValueError, match="unknown add-on"):
        resolve_edition(Edition.STARTER, ("inventory",))


def test_unknown_edition_is_rejected():
    with pytest.raises(ValueError, match="unknown product edition"):
        resolve_edition("ultimate")


def test_planned_modules_never_appear_activatable():
    modules = _by_id(resolve_edition(Edition.ENTERPRISE))
    assert modules["sales"]["can_activate"] is False
    assert modules["sales"]["status"] == ModuleStatus.PLANNED.value



def test_addon_with_unlicensed_dependency_is_not_activatable():
    modules = _by_id(resolve_edition(Edition.STARTER, ("portals",)))
    assert modules["portals"]["included_by_edition_or_addon"] is True
    assert modules["portals"]["missing_dependency_entitlements"] == ["integrations"]
    assert modules["portals"]["can_activate"] is False


def test_foundation_module_can_activate_only_when_included_and_dependencies_satisfied():
    modules = _by_id(resolve_edition(Edition.STARTER))
    assert modules["catalog"]["can_activate"] is True
    assert modules["platform"]["can_activate"] is True
    assert modules["inventory"]["can_activate"] is True
