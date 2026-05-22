"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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
async def test_user_step_invalid_auth(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            side_effect=SwitchBotAuthError("bad token")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            side_effect=SwitchBotApiError("network down")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_user_step_no_others_aborts(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[
                {
                    "deviceId": "tv-1",
                    "deviceName": "LIVING TV",
                    "remoteType": "TV",
                    "hubDeviceId": "h",
                }
            ]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_others_remotes"


@pytest.mark.asyncio
async def test_select_remotes_step_shows_others_only(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[
                {
                    "deviceId": "01-OFFICE",
                    "deviceName": "OFFICE AC",
                    "remoteType": "Others",
                    "hubDeviceId": "h",
                },
                {
                    "deviceId": "02-LIVING",
                    "deviceName": "LIVING TV",
                    "remoteType": "TV",
                    "hubDeviceId": "h",
                },
            ]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "tk", CONF_SECRET: "sk"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_remotes"
    schema = result["data_schema"].schema
    # The 'remotes' selector must include OFFICE AC and exclude LIVING TV
    selector_field = next(k for k in schema if str(k) == "remotes")
    selector = schema[selector_field]
    option_values = [opt["value"] for opt in selector.config["options"]]
    assert option_values == ["01-OFFICE"]


@pytest.mark.asyncio
async def test_full_flow_creates_entry(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[
                {
                    "deviceId": "01-OFFICE",
                    "deviceName": "OFFICE AC",
                    "remoteType": "Others",
                    "hubDeviceId": "h",
                }
            ]
        )
        # Step user
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "tk", CONF_SECRET: "sk"}
        )
        # Step select_remotes
        assert result["step_id"] == "select_remotes"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"remotes": ["01-OFFICE"]}
        )
        # Step buttons
        assert result["step_id"] == "buttons"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"buttons": "ON/OFF\nTEMP UP\nTEMP DOWN\nMODE\nFAN SPEED\n"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_TOKEN: "tk", CONF_SECRET: "sk"}
    assert result["options"] == {
        CONF_REMOTES: [
            {
                CONF_DEVICE_ID: "01-OFFICE",
                CONF_DEVICE_NAME: "OFFICE AC",
                CONF_BUTTONS: ["ON/OFF", "TEMP UP", "TEMP DOWN", "MODE", "FAN SPEED"],
            }
        ]
    }


@pytest.mark.asyncio
async def test_options_flow_updates_buttons(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: ["ON/OFF"],
                }
            ]
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "buttons"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"buttons": "ON/OFF\nTEMP UP"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_REMOTES: [
            {
                CONF_DEVICE_ID: "01-OFFICE",
                CONF_DEVICE_NAME: "OFFICE AC",
                CONF_BUTTONS: ["ON/OFF", "TEMP UP"],
            }
        ]
    }
