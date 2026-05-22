"""Config flow for SwitchBot IR (Others)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    SwitchBotApiClient,
    SwitchBotApiError,
    SwitchBotAuthError,
)
from .const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
    CONF_SECRET,
    CONF_TOKEN,
    DOMAIN,
    REMOTE_TYPE_OTHERS,
)


class SwitchbotIROthersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SwitchBot IR (Others)."""

    VERSION = 1

    def __init__(self) -> None:
        self._token: str | None = None
        self._secret: str | None = None
        self._remotes: list[dict[str, Any]] = []
        self._selected_ids: list[str] = []
        self._configured_remotes: list[dict[str, Any]] = []
        self._current_index = 0

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = SwitchBotApiClient(
                token=user_input[CONF_TOKEN],
                secret=user_input[CONF_SECRET],
                http_client=get_async_client(self.hass),
            )
            try:
                remotes = await client.list_infrared_remotes()
            except SwitchBotAuthError:
                errors["base"] = "invalid_auth"
            except SwitchBotApiError:
                errors["base"] = "cannot_connect"
            else:
                others = [
                    r for r in remotes if r.get("remoteType") == REMOTE_TYPE_OTHERS
                ]
                if not others:
                    return self.async_abort(reason="no_others_remotes")
                self._token = user_input[CONF_TOKEN]
                self._secret = user_input[CONF_SECRET]
                self._remotes = others
                return await self.async_step_select_remotes()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Required(CONF_SECRET): str,
                }
            ),
            errors=errors,
        )

    async def async_step_select_remotes(
        self, user_input: dict[str, Any] | None = None
    ):
        if user_input is not None:
            self._selected_ids = user_input["remotes"]
            self._current_index = 0
            return await self.async_step_buttons()

        options = [
            SelectOptionDict(value=r["deviceId"], label=r["deviceName"])
            for r in self._remotes
        ]
        return self.async_show_form(
            step_id="select_remotes",
            data_schema=vol.Schema(
                {
                    vol.Required("remotes"): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def async_step_buttons(
        self, user_input: dict[str, str] | None = None
    ):
        if self._current_index >= len(self._selected_ids):
            return await self._finish()

        current_id = self._selected_ids[self._current_index]
        current = next(r for r in self._remotes if r["deviceId"] == current_id)

        if user_input is not None:
            buttons = [
                line.strip()
                for line in user_input.get("buttons", "").splitlines()
                if line.strip()
            ]
            self._configured_remotes.append(
                {
                    CONF_DEVICE_ID: current["deviceId"],
                    CONF_DEVICE_NAME: current["deviceName"],
                    CONF_BUTTONS: buttons,
                }
            )
            self._current_index += 1
            return await self.async_step_buttons()

        return self.async_show_form(
            step_id="buttons",
            description_placeholders={"remote_name": current["deviceName"]},
            data_schema=vol.Schema(
                {
                    vol.Required("buttons"): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT,
                            multiline=True,
                        )
                    ),
                }
            ),
        )

    async def _finish(self):
        assert self._token is not None
        await self.async_set_unique_id(f"{DOMAIN}_{self._token[-6:]}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="SwitchBot IR (Others)",
            data={
                CONF_TOKEN: self._token,
                CONF_SECRET: self._secret,
            },
            options={CONF_REMOTES: self._configured_remotes},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SwitchbotIROthersOptionsFlow(entry)


class SwitchbotIROthersOptionsFlow(OptionsFlow):
    """Options flow: edit button lists for existing entries."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._index = 0
        self._updated: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ):
        return await self.async_step_buttons()

    async def async_step_buttons(
        self, user_input: dict[str, str] | None = None
    ):
        remotes = self._entry.options.get(CONF_REMOTES, [])
        if self._index >= len(remotes):
            return self.async_create_entry(
                title="", data={CONF_REMOTES: self._updated}
            )

        current = remotes[self._index]
        if user_input is not None:
            buttons = [
                line.strip()
                for line in user_input.get("buttons", "").splitlines()
                if line.strip()
            ]
            self._updated.append(
                {
                    CONF_DEVICE_ID: current[CONF_DEVICE_ID],
                    CONF_DEVICE_NAME: current[CONF_DEVICE_NAME],
                    CONF_BUTTONS: buttons,
                }
            )
            self._index += 1
            return await self.async_step_buttons()

        existing = "\n".join(current.get(CONF_BUTTONS, []))
        return self.async_show_form(
            step_id="buttons",
            description_placeholders={"remote_name": current[CONF_DEVICE_NAME]},
            data_schema=vol.Schema(
                {
                    vol.Required("buttons", default=existing): TextSelector(
                        TextSelectorConfig(
                            type=TextSelectorType.TEXT,
                            multiline=True,
                        )
                    ),
                }
            ),
        )
