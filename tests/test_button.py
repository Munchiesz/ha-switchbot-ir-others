"""Tests for the button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
async def test_button_entities_created_and_press_calls_api(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: ["ON/OFF", "TEMP UP", "TEMP DOWN", "MODE", "FAN SPEED"],
                }
            ]
        },
    )
    entry.add_to_hass(hass)

    mock_send = AsyncMock()
    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.send_command = mock_send
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Five button entities should exist
    entity_ids = [
        s.entity_id for s in hass.states.async_all() if s.entity_id.startswith("button.")
    ]
    assert len(entity_ids) == 5
    assert "button.office_ac_temp_up" in entity_ids

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.office_ac_temp_up"},
        blocking=True,
    )

    mock_send.assert_awaited_once_with("01-OFFICE", "TEMP UP")
