"""Tests for the button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_ir_others.api import (
    SwitchBotApiError,
    SwitchBotAuthError,
    SwitchBotRateLimitError,
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


def _office_ac_entry(
    buttons: list[str] | None = None,
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: buttons
                    or ["ON/OFF", "TEMP UP", "TEMP DOWN", "MODE", "FAN SPEED"],
                }
            ]
        },
    )


@pytest.mark.asyncio
async def test_button_entities_created_and_press_calls_api(hass: HomeAssistant) -> None:
    entry = _office_ac_entry()
    entry.add_to_hass(hass)

    mock_send = AsyncMock()
    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        mock_cls.return_value.send_command = mock_send
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_ids = [
        s.entity_id
        for s in hass.states.async_all()
        if s.entity_id.startswith("button.")
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


@pytest.mark.asyncio
async def test_button_press_rate_limit_raises_homeassistant_error(
    hass: HomeAssistant,
) -> None:
    entry = _office_ac_entry(buttons=["ON/OFF"])
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        mock_cls.return_value.send_command = AsyncMock(
            side_effect=SwitchBotRateLimitError("190: too many requests")
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(HomeAssistantError, match="rate limit"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.office_ac_on_off"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_button_press_api_error_raises_homeassistant_error(
    hass: HomeAssistant,
) -> None:
    entry = _office_ac_entry(buttons=["ON/OFF"])
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        mock_cls.return_value.send_command = AsyncMock(
            side_effect=SwitchBotApiError("boom")
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(HomeAssistantError, match="Failed to send"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.office_ac_on_off"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_button_press_auth_error_triggers_reauth(hass: HomeAssistant) -> None:
    entry = _office_ac_entry(buttons=["ON/OFF"])
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        mock_cls.return_value.send_command = AsyncMock(
            side_effect=SwitchBotAuthError("bad token")
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(HomeAssistantError, match="authentication failed"):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": "button.office_ac_on_off"},
                blocking=True,
            )

    # A reauth flow should have been queued.
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert any(flow["context"].get("source") == "reauth" for flow in flows)


@pytest.mark.asyncio
async def test_duplicate_button_slugs_collapse_to_one_entity(
    hass: HomeAssistant,
) -> None:
    entry = _office_ac_entry(buttons=["FAN SPEED", "FAN-SPEED", "fan speed"])
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    button_ids = [
        s.entity_id
        for s in hass.states.async_all()
        if s.entity_id.startswith("button.")
    ]
    assert button_ids == ["button.office_ac_fan_speed"]
