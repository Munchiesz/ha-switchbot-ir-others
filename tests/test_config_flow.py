"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.switchbot_ir_others.api import (
    SwitchBotApiError,
    SwitchBotAuthError,
)
from custom_components.switchbot_ir_others.const import CONF_SECRET, CONF_TOKEN, DOMAIN


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
