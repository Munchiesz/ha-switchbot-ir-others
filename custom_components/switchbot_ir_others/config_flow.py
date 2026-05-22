"""Config flow for SwitchBot IR (Others)."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
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
from homeassistant.util import slugify

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


def _token_unique_id(token: str) -> str:
    """Return a stable, non-leaking unique_id derived from the token."""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    return f"{DOMAIN}_{digest}"


def _parse_button_lines(raw: str) -> list[str]:
    """Parse a multi-line button input, stripping blanks and slug-duplicates."""
    seen: set[str] = set()
    result: list[str] = []
    for line in raw.splitlines():
        name = line.strip()
        if not name:
            continue
        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        result.append(name)
    return result


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
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
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
                await self.async_set_unique_id(_token_unique_id(user_input[CONF_TOKEN]))
                self._abort_if_unique_id_configured()
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
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._selected_ids = user_input["remotes"]
            self._current_index = 0
            return await self._advance_buttons()

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

    async def _advance_buttons(self) -> ConfigFlowResult:
        """Either show the buttons form for the next remote, or finish."""
        if self._current_index >= len(self._selected_ids):
            return await self._finish()
        return await self.async_step_buttons()

    async def async_step_buttons(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        if self._current_index >= len(self._selected_ids):
            return await self._finish()

        current_id = self._selected_ids[self._current_index]
        current = next(r for r in self._remotes if r["deviceId"] == current_id)

        if user_input is not None:
            buttons = _parse_button_lines(user_input.get("buttons", ""))
            self._configured_remotes.append(
                {
                    CONF_DEVICE_ID: current["deviceId"],
                    CONF_DEVICE_NAME: current["deviceName"],
                    CONF_BUTTONS: buttons,
                }
            )
            self._current_index += 1
            return await self._advance_buttons()

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

    async def _finish(self) -> ConfigFlowResult:
        if self._token is None or self._secret is None:
            return self.async_abort(reason="unknown")
        return self.async_create_entry(
            title="SwitchBot IR (Others)",
            data={
                CONF_TOKEN: self._token,
                CONF_SECRET: self._secret,
            },
            options={CONF_REMOTES: self._configured_remotes},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauth when SwitchBot rejects stored credentials."""
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None and self._reauth_entry is not None:
            client = SwitchBotApiClient(
                token=user_input[CONF_TOKEN],
                secret=user_input[CONF_SECRET],
                http_client=get_async_client(self.hass),
            )
            try:
                await client.list_infrared_remotes()
            except SwitchBotAuthError:
                errors["base"] = "invalid_auth"
            except SwitchBotApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(_token_unique_id(user_input[CONF_TOKEN]))
                self._abort_if_unique_id_mismatch(reason="account_mismatch")
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        CONF_TOKEN: user_input[CONF_TOKEN],
                        CONF_SECRET: user_input[CONF_SECRET],
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Required(CONF_SECRET): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return SwitchbotIROthersOptionsFlow()


class SwitchbotIROthersOptionsFlow(OptionsFlow):
    """Options flow: refresh available remotes, edit button lists."""

    def __init__(self) -> None:
        self._index = 0
        self._updated: list[dict[str, Any]] = []
        self._selected_ids: list[str] = []
        self._available_remotes: list[dict[str, Any]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-list remotes from the cloud so newly-added ones can be picked up."""
        client = SwitchBotApiClient(
            token=self.config_entry.data[CONF_TOKEN],
            secret=self.config_entry.data[CONF_SECRET],
            http_client=get_async_client(self.hass),
        )
        try:
            remotes = await client.list_infrared_remotes()
        except (SwitchBotAuthError, SwitchBotApiError):
            # Fall back to whatever is already in options if we can't reach the cloud.
            # Convert the stored {CONF_DEVICE_ID, CONF_DEVICE_NAME} schema to the
            # API schema {deviceId, deviceName} so the rest of the flow is uniform.
            self._available_remotes = [
                {
                    "deviceId": r[CONF_DEVICE_ID],
                    "deviceName": r[CONF_DEVICE_NAME],
                }
                for r in self.config_entry.options.get(CONF_REMOTES, [])
            ]
            self._selected_ids = [
                r["deviceId"] for r in self._available_remotes
            ]
            return await self._advance_buttons()

        others = [r for r in remotes if r.get("remoteType") == REMOTE_TYPE_OTHERS]
        self._available_remotes = others
        return await self.async_step_select_remotes()

    async def async_step_select_remotes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        existing_by_id = {
            r[CONF_DEVICE_ID]: r
            for r in self.config_entry.options.get(CONF_REMOTES, [])
        }

        if user_input is not None:
            self._selected_ids = user_input["remotes"]
            return await self._advance_buttons()

        options = [
            SelectOptionDict(value=r["deviceId"], label=r["deviceName"])
            for r in self._available_remotes
        ]
        default_selected = [
            r["deviceId"]
            for r in self._available_remotes
            if r["deviceId"] in existing_by_id
        ]
        return self.async_show_form(
            step_id="select_remotes",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "remotes", default=default_selected
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
        )

    async def _advance_buttons(self) -> ConfigFlowResult:
        if self._index >= len(self._selected_ids):
            return self.async_create_entry(
                title="", data={CONF_REMOTES: self._updated}
            )
        return await self.async_step_buttons()

    async def async_step_buttons(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        if self._index >= len(self._selected_ids):
            return self.async_create_entry(
                title="", data={CONF_REMOTES: self._updated}
            )

        current_id = self._selected_ids[self._index]
        existing_by_id = {
            r[CONF_DEVICE_ID]: r
            for r in self.config_entry.options.get(CONF_REMOTES, [])
        }
        available_by_id = {r["deviceId"]: r for r in self._available_remotes}

        if current_id in available_by_id:
            device_name = available_by_id[current_id]["deviceName"]
        elif current_id in existing_by_id:
            device_name = existing_by_id[current_id][CONF_DEVICE_NAME]
        else:
            # The selected remote disappeared from the cloud between steps; skip it.
            self._index += 1
            return await self._advance_buttons()

        if user_input is not None:
            buttons = _parse_button_lines(user_input.get("buttons", ""))
            self._updated.append(
                {
                    CONF_DEVICE_ID: current_id,
                    CONF_DEVICE_NAME: device_name,
                    CONF_BUTTONS: buttons,
                }
            )
            self._index += 1
            return await self._advance_buttons()

        existing = "\n".join(
            existing_by_id.get(current_id, {}).get(CONF_BUTTONS, [])
        )
        return self.async_show_form(
            step_id="buttons",
            description_placeholders={"remote_name": device_name},
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
