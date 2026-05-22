# SwitchBot IR (Others) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable Home Assistant custom integration (`switchbot_ir_others`) that surfaces SwitchBot "Others"-type virtual IR remotes — which the official integration ignores — as `button` entities, one entity per user-defined button.

**Architecture:** Single-domain HA custom integration with three components: an `httpx`-based SwitchBot Cloud API client that handles v1.1 HMAC signing, a `button` platform that materializes configured commands as `ButtonEntity` instances, and a multi-step config flow (credentials → pick remotes → enter button names per remote) plus an options flow for editing button lists later. No polling, no state — pure command passthrough.

**Tech Stack:** Python 3.13+, Home Assistant 2025.1.0+, `httpx` (HA-provided), `voluptuous` (HA-provided), `pytest` + `pytest-homeassistant-custom-component` for tests, `ruff` for lint, GitHub Actions for CI. Source spec: [`docs/superpowers/specs/2026-05-21-switchbot-ir-others-design.md`](../specs/2026-05-21-switchbot-ir-others-design.md).

---

## File Structure

The repo root mirrors how HACS installs the integration into a user's HA config directory.

```
ha-switchbot-ir-others/
├── custom_components/switchbot_ir_others/
│   ├── __init__.py            # async_setup_entry, async_unload_entry, update listener
│   ├── api.py                 # SwitchBotApiClient + signing + errors
│   ├── button.py              # SwitchbotIROthersButton + platform setup
│   ├── config_flow.py         # 3-step setup + options + reauth
│   ├── const.py               # DOMAIN + config keys + REMOTE_TYPE_OTHERS
│   ├── manifest.json
│   └── strings.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # pytest fixtures (mock client, mock entry)
│   ├── test_api.py
│   ├── test_button.py
│   └── test_config_flow.py
├── docs/superpowers/
│   ├── specs/2026-05-21-switchbot-ir-others-design.md
│   └── plans/2026-05-22-switchbot-ir-others.md
├── .github/workflows/ci.yml
├── .gitignore
├── hacs.json
├── pyproject.toml
├── README.md
└── LICENSE
```

Decomposition rationale:
- `api.py` is HA-agnostic — pure Python over `httpx` — so it can be tested without booting HA.
- `config_flow.py` is the largest file because the multi-step UI is inherently a state machine; keeping it separate from runtime code keeps the module boundaries clean.
- `button.py` owns the entity class only; `const.py` holds the strings everyone else imports to avoid magic literals.
- Tests mirror the source structure 1:1 so each module has exactly one test file.

---

## Task 1: Project scaffolding

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `custom_components/switchbot_ir_others/__init__.py` (empty placeholder)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
.venv/
venv/
.idea/
.vscode/
*.log
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "switchbot-ir-others"
version = "0.1.0"
description = "Home Assistant integration for SwitchBot Others-type IR remotes"
requires-python = ">=3.13"

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-homeassistant-custom-component>=0.13",
    "ruff>=0.6",
]
```

- [ ] **Step 3: Create empty `custom_components/switchbot_ir_others/__init__.py`**

Write a single line so the directory is a Python package:

```python
"""SwitchBot IR (Others) integration."""
```

- [ ] **Step 4: Create empty `tests/__init__.py`**

Empty file.

- [ ] **Step 5: Create `tests/conftest.py` with HA fixture auto-enable**

```python
"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    yield
```

- [ ] **Step 6: Verify pytest collects with no errors**

Run: `pytest --collect-only`
Expected: `0 tests collected` with no errors (empty test suite, but no import errors).

- [ ] **Step 7: Commit**

```bash
git add .gitignore pyproject.toml custom_components/switchbot_ir_others/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold project structure and tooling"
```

---

## Task 2: Constants module

**Files:**
- Create: `custom_components/switchbot_ir_others/const.py`

- [ ] **Step 1: Write `const.py`**

```python
"""Constants for the SwitchBot IR (Others) integration."""

DOMAIN = "switchbot_ir_others"

CONF_TOKEN = "token"
CONF_SECRET = "secret"
CONF_REMOTES = "remotes"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_BUTTONS = "buttons"

REMOTE_TYPE_OTHERS = "Others"

API_BASE_URL = "https://api.switch-bot.com/v1.1"
API_TIMEOUT_SECONDS = 10
API_STATUS_OK = 100
API_STATUS_UNAUTHORIZED = (161, 171)
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from custom_components.switchbot_ir_others import const; print(const.DOMAIN)"`
Expected: `switchbot_ir_others`

- [ ] **Step 3: Commit**

```bash
git add custom_components/switchbot_ir_others/const.py
git commit -m "feat: add constants module"
```

---

## Task 3: API signing function (HMAC)

**Files:**
- Create: `custom_components/switchbot_ir_others/api.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Compute the golden signature value for the test**

Run this once and copy the output — it's the expected `sign` for known fixed inputs:

```bash
python -c "import hmac, hashlib, base64; print(base64.b64encode(hmac.new(b'sk', b'tk1700000000000nonce-fixed', hashlib.sha256).digest()).decode('ascii').upper())"
```

Note the printed value — let's call it `GOLDEN_SIGN`. Substitute it in Step 2.

- [ ] **Step 2: Write failing test**

Create `tests/test_api.py`:

```python
"""Tests for the SwitchBot API client."""

from __future__ import annotations

from custom_components.switchbot_ir_others.api import _build_signature


def test_build_signature_matches_known_value() -> None:
    # Golden value computed via:
    # base64(HMAC_SHA256("sk", "tk" + "1700000000000" + "nonce-fixed")).upper()
    expected = "<paste GOLDEN_SIGN from Step 1>"
    actual = _build_signature(
        token="tk",
        secret="sk",
        t="1700000000000",
        nonce="nonce-fixed",
    )
    assert actual == expected


def test_build_signature_changes_with_nonce() -> None:
    a = _build_signature(token="tk", secret="sk", t="1700000000000", nonce="a")
    b = _build_signature(token="tk", secret="sk", t="1700000000000", nonce="b")
    assert a != b
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: ImportError or ModuleNotFoundError — `_build_signature` doesn't exist yet.

- [ ] **Step 4: Implement `_build_signature` in `api.py`**

Create `custom_components/switchbot_ir_others/api.py`:

```python
"""SwitchBot Cloud API client for the IR Others integration."""

from __future__ import annotations

import base64
import hashlib
import hmac


def _build_signature(*, token: str, secret: str, t: str, nonce: str) -> str:
    """Build the SwitchBot v1.1 'sign' header value.

    Algorithm: base64(HMAC_SHA256(secret, token + t + nonce)).upper()
    """
    string_to_sign = (token + t + nonce).encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii").upper()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/switchbot_ir_others/api.py tests/test_api.py
git commit -m "feat(api): implement HMAC signing for SwitchBot v1.1"
```

---

## Task 4: API error classes

**Files:**
- Modify: `custom_components/switchbot_ir_others/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing test for error hierarchy**

Append to `tests/test_api.py`:

```python
from custom_components.switchbot_ir_others.api import (
    SwitchBotApiError,
    SwitchBotAuthError,
)


def test_auth_error_is_api_error() -> None:
    assert issubclass(SwitchBotAuthError, SwitchBotApiError)


def test_api_error_carries_message() -> None:
    err = SwitchBotApiError("boom")
    assert str(err) == "boom"
```

- [ ] **Step 2: Run tests, verify failure**

Run: `pytest tests/test_api.py -v`
Expected: ImportError on `SwitchBotApiError`.

- [ ] **Step 3: Add error classes to `api.py`**

Append to `custom_components/switchbot_ir_others/api.py`:

```python
class SwitchBotApiError(Exception):
    """Raised when the SwitchBot API returns an error or is unreachable."""


class SwitchBotAuthError(SwitchBotApiError):
    """Raised when SwitchBot rejects the token/secret."""
```

- [ ] **Step 4: Run tests, verify pass**

Run: `pytest tests/test_api.py -v`
Expected: all four tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/api.py tests/test_api.py
git commit -m "feat(api): add error classes"
```

---

## Task 5: API client class + `list_infrared_remotes`

**Files:**
- Modify: `custom_components/switchbot_ir_others/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing test using `respx` to mock httpx**

`pytest-homeassistant-custom-component` brings `respx`. Append to `tests/test_api.py`:

```python
import httpx
import pytest
import respx

from custom_components.switchbot_ir_others.api import SwitchBotApiClient
from custom_components.switchbot_ir_others.const import API_BASE_URL


@pytest.mark.asyncio
async def test_list_infrared_remotes_returns_list() -> None:
    body = {
        "statusCode": 100,
        "message": "success",
        "body": {
            "deviceList": [],
            "infraredRemoteList": [
                {
                    "deviceId": "01-1",
                    "deviceName": "OFFICE AC",
                    "remoteType": "Others",
                    "hubDeviceId": "hub-1",
                },
                {
                    "deviceId": "02-2",
                    "deviceName": "LIVING TV",
                    "remoteType": "TV",
                    "hubDeviceId": "hub-1",
                },
            ],
        },
    }
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.get(f"{API_BASE_URL}/devices").mock(
                return_value=httpx.Response(200, json=body)
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            remotes = await client.list_infrared_remotes()
    assert len(remotes) == 2
    assert remotes[0]["deviceName"] == "OFFICE AC"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_api.py::test_list_infrared_remotes_returns_list -v`
Expected: ImportError on `SwitchBotApiClient`.

- [ ] **Step 3: Implement client skeleton + method**

Replace the bottom of `custom_components/switchbot_ir_others/api.py` (after the error classes) with:

```python
import time
import uuid
from typing import Any

import httpx

from .const import (
    API_BASE_URL,
    API_STATUS_OK,
    API_STATUS_UNAUTHORIZED,
    API_TIMEOUT_SECONDS,
)


class SwitchBotApiClient:
    """Thin async client for SwitchBot Cloud API v1.1."""

    def __init__(
        self,
        *,
        token: str,
        secret: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._token = token
        self._secret = secret
        self._http = http_client

    def _build_headers(self) -> dict[str, str]:
        t = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4())
        sign = _build_signature(
            token=self._token, secret=self._secret, t=t, nonce=nonce
        )
        return {
            "Authorization": self._token,
            "sign": sign,
            "t": t,
            "nonce": nonce,
            "Content-Type": "application/json; charset=utf8",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{API_BASE_URL}{path}"
        headers = self._build_headers()
        try:
            resp = await self._http.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=API_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise SwitchBotApiError(f"Network error: {exc}") from exc

        if resp.status_code in (401, 403):
            raise SwitchBotAuthError(f"HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise SwitchBotApiError(f"HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        status_code = data.get("statusCode")
        if status_code != API_STATUS_OK:
            message = data.get("message", "unknown error")
            if status_code in API_STATUS_UNAUTHORIZED:
                raise SwitchBotAuthError(f"SwitchBot {status_code}: {message}")
            raise SwitchBotApiError(f"SwitchBot {status_code}: {message}")
        return data.get("body") or {}

    async def list_infrared_remotes(self) -> list[dict[str, Any]]:
        body = await self._request("GET", "/devices")
        return body.get("infraredRemoteList", [])
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_api.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/api.py tests/test_api.py
git commit -m "feat(api): add client class and list_infrared_remotes"
```

---

## Task 6: API client `send_command` + error mapping

**Files:**
- Modify: `custom_components/switchbot_ir_others/api.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing tests for `send_command` + auth + non-100 status**

Append to `tests/test_api.py`:

```python
@pytest.mark.asyncio
async def test_send_command_posts_customize() -> None:
    captured: dict[str, Any] = {}

    def _record(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["url"] = str(request.url)
        captured["body"] = _json.loads(request.content)
        captured["sign"] = request.headers.get("sign")
        return httpx.Response(200, json={"statusCode": 100, "message": "ok", "body": {}})

    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/dev-1/commands").mock(side_effect=_record)
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            await client.send_command("dev-1", "TEMP UP")

    assert captured["url"].endswith("/devices/dev-1/commands")
    assert captured["body"] == {
        "commandType": "customize",
        "command": "TEMP UP",
        "parameter": "default",
    }
    assert captured["sign"]  # signed


@pytest.mark.asyncio
async def test_send_command_raises_auth_on_401() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(401, json={})
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotAuthError):
                await client.send_command("d", "X")


@pytest.mark.asyncio
async def test_send_command_raises_auth_on_status_161() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(
                    200, json={"statusCode": 161, "message": "Token invalid", "body": {}}
                )
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotAuthError):
                await client.send_command("d", "X")


@pytest.mark.asyncio
async def test_send_command_raises_api_error_on_other_status() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(
                    200,
                    json={"statusCode": 190, "message": "Rate limited", "body": {}},
                )
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotApiError) as info:
                await client.send_command("d", "X")
            assert not isinstance(info.value, SwitchBotAuthError)
            assert "190" in str(info.value)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_api.py -v`
Expected: failures — `send_command` does not exist yet (auth/error mapping for `send_command` is also untested but the method is missing first).

- [ ] **Step 3: Add `send_command` to `SwitchBotApiClient`**

Append to the `SwitchBotApiClient` class in `api.py`:

```python
    async def send_command(self, device_id: str, command: str) -> None:
        await self._request(
            "POST",
            f"/devices/{device_id}/commands",
            json={
                "commandType": "customize",
                "command": command,
                "parameter": "default",
            },
        )
```

- [ ] **Step 4: Run tests to verify all pass**

Run: `pytest tests/test_api.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/api.py tests/test_api.py
git commit -m "feat(api): add send_command and error mapping"
```

---

## Task 7: Manifest and HACS metadata files

**Files:**
- Create: `custom_components/switchbot_ir_others/manifest.json`
- Create: `hacs.json`

- [ ] **Step 1: Create `manifest.json`**

```json
{
  "domain": "switchbot_ir_others",
  "name": "SwitchBot IR (Others)",
  "version": "0.1.0",
  "documentation": "https://github.com/theilya/ha-switchbot-ir-others",
  "issue_tracker": "https://github.com/theilya/ha-switchbot-ir-others/issues",
  "codeowners": ["@theilya"],
  "config_flow": true,
  "iot_class": "cloud_push",
  "integration_type": "hub",
  "requirements": []
}
```

- [ ] **Step 2: Create `hacs.json`**

```json
{
  "name": "SwitchBot IR (Others)",
  "homeassistant": "2025.1.0",
  "render_readme": true
}
```

- [ ] **Step 3: Validate JSON**

Run: `python -c "import json; json.load(open('custom_components/switchbot_ir_others/manifest.json')); json.load(open('hacs.json'))"`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add custom_components/switchbot_ir_others/manifest.json hacs.json
git commit -m "chore: add manifest.json and hacs.json"
```

---

## Task 8: Integration entry setup (`__init__.py`)

**Files:**
- Modify: `custom_components/switchbot_ir_others/__init__.py`
- Create: `tests/test_init.py`

- [ ] **Step 1: Add failing test**

Create `tests/test_init.py`:

```python
"""Tests for integration setup/unload."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_ir_others.const import (
    CONF_REMOTES,
    CONF_SECRET,
    CONF_TOKEN,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_setup_and_unload(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={CONF_REMOTES: []},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_client:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id in hass.data[DOMAIN]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_init.py -v`
Expected: failure — `__init__.py` has no `async_setup_entry`.

- [ ] **Step 3: Replace `__init__.py` with the full implementation**

Replace `custom_components/switchbot_ir_others/__init__.py`:

```python
"""SwitchBot IR (Others) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

from .api import SwitchBotApiClient
from .const import CONF_SECRET, CONF_TOKEN, DOMAIN

PLATFORMS: list[Platform] = [Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SwitchBot IR Others from a config entry."""
    client = SwitchBotApiClient(
        token=entry.data[CONF_TOKEN],
        secret=entry.data[CONF_SECRET],
        http_client=get_async_client(hass),
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_init.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/__init__.py tests/test_init.py
git commit -m "feat: implement async_setup_entry and async_unload_entry"
```

---

## Task 9: Button platform

**Files:**
- Create: `custom_components/switchbot_ir_others/button.py`
- Create: `tests/test_button.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_button.py`:

```python
"""Tests for the button platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
async def test_button_entities_created_and_press_calls_api(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: ["ON/OFF", "TEMP UP", "TEMP DOWN", "MODE", "FAN SPEED"],
                }
            ]
        },
    )
    entry.add_to_hass(hass)

    mock_send = AsyncMock()
    with patch(
        "custom_components.switchbot_ir_others.SwitchBotApiClient"
    ) as mock_cls:
        mock_cls.return_value.send_command = mock_send
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Five button entities should exist
    entity_ids = [
        s.entity_id for s in hass.states.async_all() if s.entity_id.startswith("button.")
    ]
    assert len(entity_ids) == 5
    assert "button.office_ac_temp_up" in entity_ids

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.office_ac_temp_up"},
        blocking=True,
    )

    mock_send.assert_awaited_once_with("01-OFFICE", "TEMP UP")
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_button.py -v`
Expected: failure — `button.py` does not exist.

- [ ] **Step 3: Implement `button.py`**

Create `custom_components/switchbot_ir_others/button.py`:

```python
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_button.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/button.py tests/test_button.py
git commit -m "feat: implement button platform with one entity per command"
```

---

## Task 10: Config flow — credentials step (`user`)

**Files:**
- Create: `custom_components/switchbot_ir_others/config_flow.py`
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing test for the credentials step**

Create `tests/test_config_flow.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_config_flow.py -v`
Expected: ImportError or "domain has no config flow".

- [ ] **Step 3: Implement the credentials step**

Create `custom_components/switchbot_ir_others/config_flow.py`:

```python
"""Config flow for SwitchBot IR (Others)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.httpx_client import get_async_client

from .api import (
    SwitchBotApiClient,
    SwitchBotApiError,
    SwitchBotAuthError,
)
from .const import (
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
        # Implemented in Task 11.
        raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: three tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/config_flow.py tests/test_config_flow.py
git commit -m "feat(config_flow): implement credentials step"
```

---

## Task 11: Config flow — select_remotes step

**Files:**
- Modify: `custom_components/switchbot_ir_others/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_config_flow.py`:

```python
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
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_config_flow.py::test_select_remotes_step_shows_others_only -v`
Expected: failure — `NotImplementedError` from the stub.

- [ ] **Step 3: Replace the `async_step_select_remotes` stub with the real implementation**

Update the imports at the top of `config_flow.py`:

```python
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
```

Replace the stub in `SwitchbotIROthersConfigFlow`:

```python
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
        # Implemented in Task 12.
        raise NotImplementedError
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/config_flow.py tests/test_config_flow.py
git commit -m "feat(config_flow): implement select_remotes step"
```

---

## Task 12: Config flow — buttons step + finish

**Files:**
- Modify: `custom_components/switchbot_ir_others/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Add failing happy-path test**

Append to `tests/test_config_flow.py`:

```python
from custom_components.switchbot_ir_others.const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
)


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
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_config_flow.py::test_full_flow_creates_entry -v`
Expected: failure — `async_step_buttons` raises NotImplementedError.

- [ ] **Step 3: Implement `async_step_buttons` and `_finish`**

Add to the imports in `config_flow.py`:

```python
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
)
```

Replace the `async_step_buttons` stub with:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/config_flow.py tests/test_config_flow.py
git commit -m "feat(config_flow): implement buttons step and entry creation"
```

---

## Task 13: Options flow (edit button lists later)

**Files:**
- Modify: `custom_components/switchbot_ir_others/config_flow.py`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_config_flow.py`:

```python
from pytest_homeassistant_custom_component.common import MockConfigEntry


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
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_config_flow.py::test_options_flow_updates_buttons -v`
Expected: failure — options flow not registered.

- [ ] **Step 3: Add the options flow class and registration**

Append to `config_flow.py` (after the `SwitchbotIROthersConfigFlow` class):

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_config_flow.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_ir_others/config_flow.py tests/test_config_flow.py
git commit -m "feat(config_flow): add options flow for editing button lists"
```

---

## Task 14: User-facing strings

**Files:**
- Create: `custom_components/switchbot_ir_others/strings.json`

- [ ] **Step 1: Create `strings.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "SwitchBot credentials",
        "description": "Open the SwitchBot app: Profile → Preferences → Developer Options to get your token and secret.",
        "data": {
          "token": "Token",
          "secret": "Secret"
        }
      },
      "select_remotes": {
        "title": "Select \"Others\" remotes",
        "description": "These are the learned (\"Others\"-type) IR remotes found on your account. Pick the ones you want in Home Assistant.",
        "data": {
          "remotes": "Remotes"
        }
      },
      "buttons": {
        "title": "Buttons for {remote_name}",
        "description": "Enter the button names exactly as you set them in the SwitchBot app, one per line. Capitalization and spacing must match (e.g. \"TEMP UP\", not \"temp up\").",
        "data": {
          "buttons": "Button names"
        }
      }
    },
    "error": {
      "invalid_auth": "Invalid token or secret.",
      "cannot_connect": "Could not reach the SwitchBot API."
    },
    "abort": {
      "no_others_remotes": "No \"Others\"-type remotes were found on this SwitchBot account.",
      "already_configured": "This SwitchBot account is already configured."
    }
  },
  "options": {
    "step": {
      "buttons": {
        "title": "Buttons for {remote_name}",
        "description": "Update the button names for this remote. One per line, exactly as named in the SwitchBot app.",
        "data": {
          "buttons": "Button names"
        }
      }
    }
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `python -c "import json; json.load(open('custom_components/switchbot_ir_others/strings.json'))"`
Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add custom_components/switchbot_ir_others/strings.json
git commit -m "feat: add user-facing strings for config and options flow"
```

---

## Task 15: README and LICENSE

**Files:**
- Create: `README.md`
- Create: `LICENSE`

- [ ] **Step 1: Write `README.md`**

```markdown
# SwitchBot IR (Others) — Home Assistant integration

A HACS-installable custom integration that adds Home Assistant support for SwitchBot **"Others"-type** IR remotes — the user-learned remotes the official `switchbot_cloud` integration skips.

If you set up an AC, fan, or any other appliance under the "Others" category in the SwitchBot app and defined your own buttons (`ON/OFF`, `TEMP UP`, etc.), this integration surfaces each of those buttons as a `button` entity in Home Assistant.

## What it does

- Talks to the SwitchBot Cloud API (v1.1, signed) — same auth as the official integration.
- Lists every `remoteType: "Others"` virtual remote on your account.
- Creates one `button` entity per user-defined button. Pressing the entity sends the IR command via your SwitchBot Hub.
- No polling, no state tracking. IR is one-way; this integration is a pure command passthrough.

## What it does NOT do

- It does not replace the official `switchbot_cloud` integration. Standard categories (AC, TV, Fan, Light) continue to be handled by the official integration. Run both side-by-side.
- It does not model a `climate` entity. Buttons map 1:1 to commands. If you want HVAC modes and setpoint translation, that's out of scope.
- It does not discover button names. The SwitchBot API does not expose them; you enter the list once during setup.

## Installation

### Via HACS (recommended)

1. HACS → Integrations → ••• → Custom repositories
2. Add `https://github.com/theilya/ha-switchbot-ir-others` as an Integration
3. Install "SwitchBot IR (Others)"
4. Restart Home Assistant

### Manual

Copy `custom_components/switchbot_ir_others/` into your HA `config/custom_components/` directory. Restart HA.

## Setup

1. Get your SwitchBot token and secret: SwitchBot app → Profile → Preferences → Developer Options.
2. In HA: Settings → Devices & Services → Add Integration → "SwitchBot IR (Others)".
3. Paste the token and secret.
4. Tick the "Others" remotes you want to add.
5. For each remote, paste the button names — one per line, exactly as named in the SwitchBot app (capitalization and spacing matter).

If you later rename or add buttons in the SwitchBot app, open the integration → Configure to update the lists.

## Entities

For a remote called "OFFICE AC" with buttons `ON/OFF`, `TEMP UP`, `TEMP DOWN`, `MODE`, `FAN SPEED`, you get:

- `button.office_ac_on_off`
- `button.office_ac_temp_up`
- `button.office_ac_temp_down`
- `button.office_ac_mode`
- `button.office_ac_fan_speed`

All five live under a single device card so they group cleanly in the UI.

## Troubleshooting

- **"Invalid token or secret"** — regenerate them in the SwitchBot app; make sure you copied both fields fully.
- **"No 'Others'-type remotes were found"** — your account has no remotes set up under the Others category. Add one in the SwitchBot app first.
- **Press succeeds but nothing happens** — the button name doesn't exactly match the SwitchBot app. Check capitalization, spaces, and slashes.
- **Rate limited** — SwitchBot enforces 10,000 API calls per token per day. Be mindful in automations.

## License

MIT. See [LICENSE](LICENSE).
```

- [ ] **Step 2: Write `LICENSE` (MIT)**

```text
MIT License

Copyright (c) 2026 theilya

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Commit**

```bash
git add README.md LICENSE
git commit -m "docs: add README and MIT license"
```

---

## Task 16: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install uv
        run: pip install uv
      - name: Install dev deps
        run: uv pip install --system --group dev
      - name: Lint
        run: ruff check custom_components tests
      - name: Test
        run: pytest -v

  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: HACS validation
        uses: hacs/action@main
        with:
          category: integration
```

- [ ] **Step 2: Verify YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: no output (success). If `yaml` is not installed locally, skip and trust the structure.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions for tests, lint, and HACS validation"
```

---

## Task 17: Final integration test — full setup smoke test

**Files:**
- Modify: `tests/test_init.py`

- [ ] **Step 1: Add an end-to-end smoke test**

Append to `tests/test_init.py`:

```python
from custom_components.switchbot_ir_others.const import (
    CONF_BUTTONS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REMOTES,
)


@pytest.mark.asyncio
async def test_full_setup_creates_all_office_ac_buttons(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_TOKEN: "tk", CONF_SECRET: "sk"},
        options={
            CONF_REMOTES: [
                {
                    CONF_DEVICE_ID: "01-OFFICE",
                    CONF_DEVICE_NAME: "OFFICE AC",
                    CONF_BUTTONS: [
                        "ON/OFF",
                        "TEMP UP",
                        "TEMP DOWN",
                        "MODE",
                        "FAN SPEED",
                    ],
                }
            ]
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.switchbot_ir_others.SwitchBotApiClient"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    for expected in [
        "button.office_ac_on_off",
        "button.office_ac_temp_up",
        "button.office_ac_temp_down",
        "button.office_ac_mode",
        "button.office_ac_fan_speed",
    ]:
        assert hass.states.get(expected) is not None, f"missing {expected}"
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: every test PASSes. Confirms the whole integration wires together.

- [ ] **Step 3: Run the linter**

Run: `ruff check custom_components tests`
Expected: `All checks passed!` (or fix any reported issues, then commit fixes separately).

- [ ] **Step 4: Commit**

```bash
git add tests/test_init.py
git commit -m "test: add full-setup smoke test for OFFICE AC"
```

---

## Self-review notes (for the plan writer)

Spec coverage check:

- "Auth (token + secret), stored encrypted by HA" → Task 10 (config flow user step writes to `entry.data`).
- "List `/v1.1/devices`, filter `remoteType == Others`" → Tasks 5, 10, 11.
- "Multi-select remotes" → Task 11.
- "Per-remote textarea of button names" → Tasks 12, 13.
- "Options flow to edit later" → Task 13.
- "Reauth flow" → **deferred to a follow-up** (deliberate scope cut for v0.1.0; mentioned in spec but not required for "just pass the commands" goal — add as v0.2.0 work).
- "Button entity per command, grouped under one device" → Task 9 (DeviceInfo identifiers).
- "HMAC signing per docs" → Tasks 3, 5 (and exercised in every request test).
- "Error handling table" → Tasks 4, 6, 10.
- "Testing strategy" → Tasks 3-13, 17.
- "Project layout" → Tasks 1, 7, 14, 15, 16.

No placeholders, no TBDs, no "similar to Task N" forward refs. Types and method names are consistent across tasks (`SwitchBotApiClient.send_command`, `SwitchBotApiClient.list_infrared_remotes`, `_build_signature` with keyword-only args).

Two follow-up tasks knowingly deferred from v0.1.0, to be tracked as separate plans if/when the user wants them:
1. Reauth flow on `SwitchBotAuthError` at runtime.
2. Widening `REMOTE_TYPE_OTHERS` filter once we observe what the API actually returns for the user's OFFICE AC (could be `"Others"`, `"DIY"`, or `""` — spec open question #1).
