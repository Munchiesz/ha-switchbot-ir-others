"""End-to-end smoke test: button press through the real API client + HTTP signing.

The other test modules patch SwitchBotApiClient out so a bug in
get_async_client wiring or the constructor kwargs would never surface.
This test wires the real client into HA and uses respx to assert the
outbound HTTP call is correctly built and signed.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_ir_others.const import (
    API_BASE_URL,
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
    CONF_SECRET,
    CONF_TOKEN,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_button_press_sends_signed_request_through_real_client(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk-real", CONF_SECRET: "sk-real"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: ["TEMP UP"],
                }
            ]
        },
    )
    entry.add_to_hass(hass)

    success = {"statusCode": 100, "message": "ok", "body": {}}
    # Setup validates credentials with GET /devices before any button press.
    devices = {"statusCode": 100, "message": "ok", "body": {"infraredRemoteList": []}}
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API_BASE_URL}/devices").mock(
            return_value=httpx.Response(200, json=devices)
        )
        route = router.post(
            f"{API_BASE_URL}/devices/01-OFFICE/commands"
        ).mock(return_value=httpx.Response(200, json=success))

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.office_ac_temp_up"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert route.call_count == 1
    request = route.calls.last.request
    # Token in Authorization header, request signed with all four mandatory pieces.
    assert request.headers["Authorization"] == "tk-real"
    assert request.headers["sign"]
    assert request.headers["t"]
    assert request.headers["nonce"]
    # Body is the customize-command shape the SwitchBot v1.1 docs require.
    body = json.loads(request.content)
    assert body == {
        "commandType": "customize",
        "command": "TEMP UP",
        "parameter": "default",
    }
