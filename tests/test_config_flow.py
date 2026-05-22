"""Tests for the config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_ir_others.api import (
    SwitchBotApiError,
    SwitchBotAuthError,
)
from custom_components.switchbot_ir_others.config_flow import _token_unique_id
from custom_components.switchbot_ir_others.const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
    CONF_SECRET,
    CONF_TOKEN,
    DOMAIN,
)


def _office_ac_remote() -> dict:
    return {
        "deviceId": "01-OFFICE",
        "deviceName": "OFFICE AC",
        "remoteType": "Others",
        "hubDeviceId": "h",
    }


def _living_tv_remote() -> dict:
    return {
        "deviceId": "02-LIVING",
        "deviceName": "LIVING TV",
        "remoteType": "TV",
        "hubDeviceId": "h",
    }


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
            return_value=[_living_tv_remote()]
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
async def test_user_step_aborts_if_token_already_configured(
    hass: HomeAssistant,
) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={CONF_REMOTES: []},
        unique_id=_token_unique_id("tk"),
    )
    existing.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[_office_ac_remote()]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_select_remotes_step_shows_others_only(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[_office_ac_remote(), _living_tv_remote()]
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
            return_value=[_office_ac_remote()]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "tk", CONF_SECRET: "sk"}
        )
        assert result["step_id"] == "select_remotes"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"remotes": ["01-OFFICE"]}
        )
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
async def test_full_flow_with_two_remotes_shows_buttons_step_twice(
    hass: HomeAssistant,
) -> None:
    second = {
        "deviceId": "03-BEDROOM",
        "deviceName": "BEDROOM HEATER",
        "remoteType": "Others",
        "hubDeviceId": "h",
    }
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[_office_ac_remote(), second]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "tk", CONF_SECRET: "sk"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"remotes": ["01-OFFICE", "03-BEDROOM"]}
        )
        # First remote
        assert result["step_id"] == "buttons"
        assert result["description_placeholders"] == {"remote_name": "OFFICE AC"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"buttons": "ON/OFF"}
        )
        # Second remote
        assert result["step_id"] == "buttons"
        assert result["description_placeholders"] == {
            "remote_name": "BEDROOM HEATER"
        }
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"buttons": "ON"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert [r[CONF_DEVICE_ID] for r in result["options"][CONF_REMOTES]] == [
        "01-OFFICE",
        "03-BEDROOM",
    ]


@pytest.mark.asyncio
async def test_full_flow_dedups_slug_duplicate_buttons(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[_office_ac_remote()]
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "tk", CONF_SECRET: "sk"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"remotes": ["01-OFFICE"]}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"buttons": "FAN SPEED\nfan speed\nFAN-SPEED\nTEMP UP\n"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_REMOTES][0][CONF_BUTTONS] == [
        "FAN SPEED",
        "TEMP UP",
    ]


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

    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(
            return_value=[_office_ac_remote()]
        )
        result = await hass.config_entries.options.async_init(entry.entry_id)
        # New step: select_remotes, with the previously-configured remote pre-selected
        assert result["step_id"] == "select_remotes"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"remotes": ["01-OFFICE"]}
        )
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


@pytest.mark.parametrize(
    "raised",
    [SwitchBotApiError("network down"), SwitchBotAuthError("rotated token")],
)
@pytest.mark.asyncio
async def test_options_flow_falls_back_when_cloud_unreachable(
    hass: HomeAssistant, raised: Exception
) -> None:
    """If the cloud can't be reached or rejects auth, options flow still works."""
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

    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.list_infrared_remotes = AsyncMock(side_effect=raised)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "buttons"
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"buttons": "ON/OFF\nTEMP UP"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_reauth_flow_updates_credentials(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "old-tk", CONF_SECRET: "old-sk"},
        options={CONF_REMOTES: []},
        unique_id=_token_unique_id("old-tk"),
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as flow_mock, patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as init_mock:
        flow_mock.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        init_mock.return_value.list_infrared_remotes = AsyncMock(return_value=[])

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"

        # Same token, rotated secret — unique_id matches, entry data updates.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "old-tk", CONF_SECRET: "new-sk"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_SECRET] == "new-sk"


@pytest.mark.asyncio
async def test_reauth_flow_rejects_invalid_credentials(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "old-tk", CONF_SECRET: "old-sk"},
        options={CONF_REMOTES: []},
        unique_id=_token_unique_id("old-tk"),
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as flow_mock:
        flow_mock.return_value.list_infrared_remotes = AsyncMock(
            side_effect=SwitchBotAuthError("still bad")
        )
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "old-tk", CONF_SECRET: "wrong-sk"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_reauth_flow_rejects_different_account(hass: HomeAssistant) -> None:
    """If the user pastes a different SwitchBot account's credentials, abort."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "old-tk", CONF_SECRET: "old-sk"},
        options={CONF_REMOTES: []},
        unique_id=_token_unique_id("old-tk"),
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.config_flow.SwitchBotApiClient"
    ) as flow_mock:
        flow_mock.return_value.list_infrared_remotes = AsyncMock(return_value=[])
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"
        # A completely different token → different unique_id → mismatch.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_TOKEN: "totally-different-tk", CONF_SECRET: "new-sk"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "account_mismatch"
    # Existing entry's credentials must be unchanged.
    assert entry.data[CONF_TOKEN] == "old-tk"
    assert entry.data[CONF_SECRET] == "old-sk"


def test_token_unique_id_differs_for_different_tokens() -> None:
    assert _token_unique_id("tk-1") != _token_unique_id("tk-2")
    assert _token_unique_id("tk-1") == _token_unique_id("tk-1")
    # Two tokens that share a 6-char suffix should NOT collide.
    assert _token_unique_id("AAAAAAAA123456") != _token_unique_id("BBBBBBBB123456")
