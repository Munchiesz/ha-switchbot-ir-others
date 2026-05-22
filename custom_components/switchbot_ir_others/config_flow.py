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
        # Implemented in Task 12
        raise NotImplementedError

    async def _finish(self):
        # Implemented in Task 12
        raise NotImplementedError

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        # Implemented in Task 13
        raise NotImplementedError


class SwitchbotIROthersOptionsFlow(OptionsFlow):
    """Options flow stub — implemented in Task 13."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        raise NotImplementedError
