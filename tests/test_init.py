"""Tests for integration setup/unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_ir_others.api import (
    SwitchBotApiError,
    SwitchBotAuthError,
)
from custom_components.switchbot_ir_others.const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
    CONF_SECRET,
    CONF_TOKEN,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_setup_and_unload(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={CONF_REMOTES: []},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.asyncio
async def test_setup_raises_auth_failed_on_bad_token(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={CONF_REMOTES: []},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            side_effect=SwitchBotAuthError("nope")
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # ConfigEntryAuthFailed → SETUP_ERROR and a reauth flow gets scheduled.
    assert entry.state is ConfigEntryState.SETUP_ERROR


@pytest.mark.asyncio
async def test_setup_retries_on_transient_error(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={CONF_REMOTES: []},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            side_effect=SwitchBotApiError("network down")
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # ConfigEntryNotReady → SETUP_RETRY.
    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.asyncio
async def test_full_setup_creates_all_office_ac_buttons(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: [
                        "ON/OFF",
                        "TEMP UP",
                        "TEMP DOWN",
                        "MODE",
                        "FAN SPEED",
                    ],
                }
            ]
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    for expected in [
        "button.office_ac_on_off",
        "button.office_ac_temp_up",
        "button.office_ac_temp_down",
        "button.office_ac_mode",
        "button.office_ac_fan_speed",
    ]:
        assert hass.states.get(expected) is not None, f"missing {expected}"
