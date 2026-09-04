"""Shared fixtures for the LK Systems test suite."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import aiohttp.connector
import pytest
from aiohttp import ThreadedResolver

# The pylksystems client is a plain aiohttp-based module with no Home
# Assistant dependency, but it lives inside the `custom_components.lksystems`
# package. Importing that package the normal way (``import
# custom_components.lksystems.pylksystems``) runs the parent package's
# __init__.py first, which imports `homeassistant` — not installed in this
# lightweight test environment. Loading the module directly from its file
# path sidesteps that and keeps these tests fast and dependency-free.
_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "lksystems"
    / "pylksystems"
    / "__init__.py"
)


def _load_pylksystems():
    spec = importlib.util.spec_from_file_location("pylksystems", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pylksystems = _load_pylksystems()


@pytest.fixture(autouse=True)
def _use_threaded_dns_resolver(monkeypatch):
    """Make every ClientSession in this suite use aiohttp's threaded resolver.

    aiohttp otherwise defaults to the aiodns-backed resolver, whose pycares
    channel spawns a permanent daemon thread the first time it is torn
    down. That happens even for a fully-mocked session that never performs
    a real lookup, and the thread outlives the test, so
    pytest-homeassistant-custom-component's leaked-thread check flags it.
    """
    monkeypatch.setattr(aiohttp.connector, "DefaultResolver", ThreadedResolver)


@pytest.fixture
def manager():
    """A fresh, unauthenticated LKSystemsManager instance."""
    return pylksystems.LKSystemsManager("user@example.com", "hunter2")
