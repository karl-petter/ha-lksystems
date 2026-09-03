"""Tests for valve.py: the Cubic Secure's main shutoff valve as a native
`valve.*` entity, rather than only the pre-existing read-only
`sensor.*_valve_state` and the open_valve/close_valve services.
"""

from __future__ import annotations

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.lksystems.const import DOMAIN

from .conftest import (
    CUBIC_IDENTITY,
    CUBIC_IDENTITY_2,
    build_cubic_configuration,
    entity_id,
    patch_all_managers,
    setup_entry,
)


def _valve_unique_id(device_identity: str) -> str:
    return f"LkUid_valve_{device_identity}"


async def test_belongs_to_the_cubic_secure_device(hass, fake_manager):
    await setup_entry(hass, fake_manager)
    valve_entity_id = entity_id(hass, "valve", _valve_unique_id(CUBIC_IDENTITY))

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, CUBIC_IDENTITY)})
    entry = er.async_get(hass).async_get(valve_entity_id)

    assert entry.device_id == device.id


@pytest.mark.parametrize("valve_state", ["open", "closed"])
async def test_reflects_state_from_client_data(hass, fake_manager, valve_state):
    fake_manager.cubic_configuration_data = build_cubic_configuration(valve_state=valve_state)
    await setup_entry(hass, fake_manager)
    valve_entity_id = entity_id(hass, "valve", _valve_unique_id(CUBIC_IDENTITY))

    state = hass.states.get(valve_entity_id)

    assert state.state == valve_state


async def test_unknown_when_configuration_data_is_missing(hass, fake_manager):
    fake_manager.get_cubic_secure_configuration_result = False
    await setup_entry(hass, fake_manager)
    valve_entity_id = entity_id(hass, "valve", _valve_unique_id(CUBIC_IDENTITY))

    state = hass.states.get(valve_entity_id)

    assert state.state == "unknown"


@pytest.mark.parametrize(
    ("ha_service", "client_call", "starting_state", "resulting_state"),
    [
        ("close_valve", "cubic_secure_close_valve", "open", "closed"),
        ("open_valve", "cubic_secure_open_valve", "closed", "open"),
    ],
)
async def test_action_calls_the_client_and_refreshes(
    hass, fake_manager, ha_service, client_call, starting_state, resulting_state
):
    fake_manager.cubic_configuration_data = build_cubic_configuration(
        valve_state=starting_state
    )
    await setup_entry(hass, fake_manager)
    valve_entity_id = entity_id(hass, "valve", _valve_unique_id(CUBIC_IDENTITY))
    # A fresh cached (force_update=False) response still showing the
    # pre-action state - proves the entity forces a fresh fetch rather
    # than relying on a regular refresh, which would keep serving this.
    fake_manager.cubic_configurations_cached_by_device[CUBIC_IDENTITY] = (
        build_cubic_configuration(valve_state=starting_state)
    )
    fake_manager.cubic_configurations_by_device[CUBIC_IDENTITY] = build_cubic_configuration(
        valve_state=resulting_state
    )

    with patch_all_managers(fake_manager):
        await hass.services.async_call(
            "valve", ha_service, {"entity_id": valve_entity_id}, blocking=True
        )

    assert (client_call, CUBIC_IDENTITY) in fake_manager.calls
    assert hass.states.get(valve_entity_id).state == resulting_state


async def test_two_cubic_secure_devices_get_independent_valves(
    hass, fake_manager_with_two_cubic_devices
):
    await setup_entry(hass, fake_manager_with_two_cubic_devices)
    first_id = entity_id(hass, "valve", _valve_unique_id(CUBIC_IDENTITY))
    second_id = entity_id(hass, "valve", _valve_unique_id(CUBIC_IDENTITY_2))

    # configure_fake_manager_with_two_cubic_devices() sets the first device
    # open and the second closed - see conftest.py.
    assert hass.states.get(first_id).state == "open"
    assert hass.states.get(second_id).state == "closed"
