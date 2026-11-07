import sys
from types import ModuleType

import pytest

from backend.app.outbox.runner import load_handlers


def test_load_handlers_accepts_nonempty_handler_factory(monkeypatch):
    module = ModuleType("test_outbox_handlers")
    def handler(_db, _message):
        return None

    def build_handlers():
        return {"sample.created": handler}

    module.build_handlers = build_handlers
    monkeypatch.setitem(sys.modules, module.__name__, module)

    assert load_handlers("test_outbox_handlers:build_handlers") == {"sample.created": handler}


@pytest.mark.parametrize(
    "factory_path",
    ["", "missing_separator", ":factory", "module:"],
)
def test_load_handlers_rejects_invalid_factory_path(factory_path):
    with pytest.raises(ValueError):
        load_handlers(factory_path)


def test_load_handlers_rejects_empty_registry(monkeypatch):
    module = ModuleType("empty_outbox_handlers")
    def build_handlers():
        return {}

    module.build_handlers = build_handlers
    monkeypatch.setitem(sys.modules, module.__name__, module)

    with pytest.raises(ValueError, match="cannot be empty"):
        load_handlers("empty_outbox_handlers:build_handlers")


def test_load_handlers_rejects_non_callable_handler(monkeypatch):
    module = ModuleType("invalid_outbox_handlers")
    def build_handlers():
        return {"sample.created": "not-callable"}

    module.build_handlers = build_handlers
    monkeypatch.setitem(sys.modules, module.__name__, module)

    with pytest.raises(ValueError, match="callables"):
        load_handlers("invalid_outbox_handlers:build_handlers")
