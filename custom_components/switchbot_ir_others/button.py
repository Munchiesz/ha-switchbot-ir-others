"""Button platform for SwitchBot IR (Others)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .api import (
    SwitchBotApiClient,
    SwitchBotApiError,
    SwitchBotAuthError,
    SwitchBotRateLimitError,
)
from .const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from the config entry's configured remotes."""
    client: SwitchBotApiClient = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchbotIROthersButton] = []
    seen_unique_ids: set[str] = set()
    for remote in entry.options.get(CONF_REMOTES, []):
        device_id = remote[CONF_DEVICE_ID]
        device_name = remote[CONF_DEVICE_NAME]
        for button_name in remote.get(CONF_BUTTONS, []):
            unique_id = f"{device_id}_{slugify(button_name)}"
            if unique_id in seen_unique_ids:
                _LOGGER.warning(
                    "Skipping duplicate button %r on %s (collides with existing entity)",
                    button_name,
                    device_name,
                )
                continue
            seen_unique_ids.add(unique_id)
            entities.append(
                SwitchbotIROthersButton(
                    client, entry, device_id, device_name, button_name
                )
            )
    async_add_entities(entities)


class SwitchbotIROthersButton(ButtonEntity):
    """A single user-defined IR button."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        client: SwitchBotApiClient,
        entry: ConfigEntry,
        device_id: str,
        device_name: str,
        button_name: str,
    ) -> None:
        self._client = client
        self._entry = entry
        self._device_id = device_id
        self._button_name = button_name
        self._attr_unique_id = f"{device_id}_{slugify(button_name)}"
        self._attr_name = button_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="SwitchBot",
            model="IR Remote (Others)",
        )

    async def async_press(self) -> None:
        try:
            await self._client.send_command(self._device_id, self._button_name)
        except SwitchBotAuthError as exc:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                f"SwitchBot authentication failed for '{self._button_name}': {exc}"
            ) from exc
        except SwitchBotRateLimitError as exc:
            raise HomeAssistantError(
                f"SwitchBot rate limit hit sending '{self._button_name}': {exc}"
            ) from exc
        except SwitchBotApiError as exc:
            raise HomeAssistantError(
                f"Failed to send '{self._button_name}': {exc}"
            ) from exc
