"""Tests for time.py: the "Automatic Pressure Test Time" time entity.

Reads/writes the device's pressure-test schedule (hour:minute), fetched
at its own endpoint separate from configuration/thresholds - see
cubic_secure_pressure_test_schedule()'s own docstring in __init__.py.
"""

from __future__ import annotations

from datetime import time

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.lksystems.const import DOMAIN

from .conftest import CUBIC_IDENTITY, entity_id, patch_all_managers, setup_entry


def _time_unique_id(device_identity: str) -> str:
    return f"LkUid_pressureTestSchedule_{device_identity}"


async def test_belongs_to_the_cubic_secure_device(hass, fake_manager):
    await setup_entry(hass, fake_manager)
    time_entity_id = entity_id(hass, "time", _time_unique_id(CUBIC_IDENTITY))

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, CUBIC_IDENTITY)})
    registry_entry = er.async_get(hass).async_get(time_entity_id)

    assert registry_entry.device_id == device.id


async def test_reflects_the_fetched_schedule(hass, fake_manager):
    fake_manager.cubic_pressure_test_schedule_data = {"hour": 3, "minute": 11}
    await setup_entry(hass, fake_manager)

    state = hass.states.get(entity_id(hass, "time", _time_unique_id(CUBIC_IDENTITY)))

    assert state.state == "03:11:00"


async def test_unknown_until_fetched_once(hass, fake_manager):
    fake_manager.get_cubic_secure_pressure_test_schedule_result = False
    await setup_entry(hass, fake_manager)

    state = hass.states.get(entity_id(hass, "time", _time_unique_id(CUBIC_IDENTITY)))

    assert state.state == "unknown"


async def test_setting_the_value_writes_the_new_hour_and_minute(hass, fake_manager):
    await setup_entry(hass, fake_manager)
    time_entity_id = entity_id(hass, "time", _time_unique_id(CUBIC_IDENTITY))

    with patch_all_managers(fake_manager):
        await hass.services.async_call(
            "time",
            "set_value",
            {"entity_id": time_entity_id, "time": time(3, 11)},
            blocking=True,
        )

    assert (
        "cubic_secure_set_pressure_test_schedule",
        CUBIC_IDENTITY,
        3,
        11,
    ) in fake_manager.calls
