"""Config flow for SwitchBot IR (Others) — stub (full implementation in Task 10)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class SwitchBotIrOthersConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SwitchBot IR Others."""

    VERSION = 1
