"""Button platform for SwitchBot IR (Others)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .api import SwitchBotApiClient, SwitchBotApiError
from .const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from the config entry's configured remotes."""
    client: SwitchBotApiClient = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchbotIROthersButton] = []
    for remote in entry.options.get(CONF_REMOTES, []):
        device_id = remote[CONF_DEVICE_ID]
        device_name = remote[CONF_DEVICE_NAME]
        for button_name in remote.get(CONF_BUTTONS, []):
            entities.append(
                SwitchbotIROthersButton(client, device_id, device_name, button_name)
            )
    async_add_entities(entities)


class SwitchbotIROthersButton(ButtonEntity):
    """A single user-defined IR button."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        client: SwitchBotApiClient,
        device_id: str,
        device_name: str,
        button_name: str,
    ) -> None:
        self._client = client
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
        except SwitchBotApiError as exc:
            raise HomeAssistantError(
                f"Failed to send '{self._button_name}': {exc}"
            ) from exc
