# SwitchBot IR "Others" Remote — Home Assistant Integration

**Date:** 2026-05-21
**Status:** Approved (brainstorming phase)
**Repo name:** `ha-switchbot-ir-others`
**Domain:** `switchbot_ir_others`

## Problem

The official Home Assistant `switchbot_cloud` integration surfaces SwitchBot Hub IR remotes only for known categories — Air Conditioner, TV, Light, Fan, etc. — by mapping each category to a built-in HA platform (climate, media_player, light, fan). Any virtual remote a user creates under the **"Others"** category in the SwitchBot app — i.e. learned/custom remotes whose buttons are user-defined — is silently skipped: it never appears as an entity in Home Assistant.

This blocks a real use case: a user's air conditioner whose factory codes aren't recognized by SwitchBot is set up as a learned "Others" remote with user-named buttons (e.g. `ON/OFF`, `TEMP UP`, `TEMP DOWN`, `MODE`, `FAN SPEED`). Those buttons exist in the SwitchBot app and work over IR, but there is no HA-side handle to call them.

## Goal

Ship a HACS-installable custom integration that exposes each button of an "Others"-type SwitchBot IR remote as a Home Assistant `button` entity. Pressing the entity sends the corresponding SwitchBot Cloud API call, which the Hub Mini / Hub 2 relays as an IR pulse.

## Non-goals

- **No climate/media_player/light/fan modeling.** This is a pure command passthrough. No internal state tracking, no setpoint translation, no HVAC mode mapping. The user wants the existing buttons surfaced verbatim.
- **No automatic button discovery.** The SwitchBot v1.1 API does not expose the custom button list for "Others" remotes — only the device metadata. Button names must be entered by the user during setup.
- **No replacement of the official `switchbot_cloud` integration.** This integration runs alongside it. Users keep the official integration for standard categories.
- **No YAML configuration.** UI-based config flow only, in line with current HA conventions.
- **No local control.** Requires SwitchBot Cloud API access. Local Bluetooth control of the Hub for IR is not supported by SwitchBot itself.

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Home Assistant                                                  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │ custom_components/switchbot_ir_others/                 │    │
│  │                                                        │    │
│  │  config_flow.py ──► api.py ◄── button.py               │    │
│  │       │              │            │                    │    │
│  │       │              │            └─► button entities  │    │
│  │       │              │                                 │    │
│  │       ▼              ▼                                 │    │
│  │   ConfigEntry    httpx + HMAC                          │    │
│  └──────────────────────┬─────────────────────────────────┘    │
│                         │                                       │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          ▼  HTTPS (signed)
              api.switch-bot.com/v1.1
                          │
                          ▼
                    SwitchBot Hub ──► IR ──► AC unit
```

The integration is small and has three components: a **config flow** that owns user setup and reconfiguration, an **API client** that handles SwitchBot's HMAC signing and JSON calls, and a **button platform** that materializes the configured commands as entities.

## Components

### 1. API client (`api.py`)

A thin client over `httpx.AsyncClient` (HA-provided shared session). Responsibilities:

- Build SwitchBot v1.1 signed request headers for every call.
- Expose two methods:
  - `async list_infrared_remotes() -> list[InfraredRemote]` — calls `GET /v1.1/devices`, returns the `infraredRemoteList`. Each item has `deviceId`, `deviceName`, `remoteType`, `hubDeviceId`.
  - `async send_command(device_id: str, command: str) -> None` — calls `POST /v1.1/devices/{device_id}/commands` with body `{"commandType": "customize", "command": command, "parameter": "default"}`. Raises on non-2xx or on a non-100 `statusCode` in the response body.

**Signing algorithm** (SwitchBot v1.1):
```
t      = current epoch milliseconds (str)
nonce  = uuid4() (str)
sign   = base64( HMAC_SHA256(secret, token + t + nonce) ).upper()

Headers:
  Authorization: <token>
  sign:          <sign>
  t:             <t>
  nonce:         <nonce>
  Content-Type:  application/json; charset=utf8
```

**Error mapping:** non-2xx HTTP → `SwitchBotApiError`. SwitchBot `statusCode != 100` → `SwitchBotApiError` with the returned message. Auth failures (401/403, or statusCode 161/171) → `SwitchBotAuthError` so the config flow can raise `InvalidAuth` and the entity can mark itself unavailable.

### 2. Config flow (`config_flow.py`)

Three-step user setup:

**Step `user`** — credentials.
- Form: `token` (str), `secret` (str). Both stored encrypted in the ConfigEntry by HA.
- On submit: instantiate the API client, call `list_infrared_remotes()`. If auth fails → `errors={"base": "invalid_auth"}`. If network/other → `errors={"base": "cannot_connect"}`.
- Filter the response: keep only entries whose `remoteType` matches the "Others" marker. **Open question to resolve during implementation:** confirm the exact string returned by the API for learned-from-scratch remotes — it may be `"Others"`, `"DIY"`, or an empty string. The implementation should accept the documented value(s) and log unrecognised types at INFO so the user can adjust the filter.
- If zero matches: abort with `no_others_remotes` reason.

**Step `select_remotes`** — pick which remotes to import.
- Multi-select checkbox list of remote names from step 1.
- The selected set is stashed in the flow state for the next step.

**Step `buttons`** — one form per selected remote, in sequence.
- Form: a single multi-line text field labelled "Button names (one per line)". Placeholder text shows the expected format and warns the casing/spacing must match the SwitchBot app exactly.
- The input is split on newlines, trimmed, blanks removed.
- After the last remote, finish: write a ConfigEntry whose `data` is `{token, secret}` and whose `options` is `{remotes: [{device_id, device_name, buttons: [...]}, ...]}`.

**Options flow:** lets the user edit the button list per remote later, without removing and re-adding the integration. Same form shape as the `buttons` step, pre-filled with existing values. On save, HA reloads the entry and the button platform re-creates entities.

**Reauth flow:** if `SwitchBotAuthError` surfaces at runtime, trigger HA's reauth flow with a single form (new token/secret). On success, reload the entry.

### 3. Button platform (`button.py`)

For each configured remote, for each configured button name, create a `SwitchbotIROthersButton` instance.

- **`unique_id`:** `f"{device_id}_{slug(button_name)}"` — stable across HA restarts and rename operations.
- **`name`:** `button_name` (the human label from the SwitchBot app). HA composes the full entity name as `<remote_device_name> <button_name>` via the device link.
- **`device_info`:** ties each button to a single HA device per SwitchBot remote, so all five buttons for "OFFICE AC" appear under one device card. Manufacturer = "SwitchBot", model = `remoteType`, name = `device_name`.
- **`async_press`:** calls `api.send_command(device_id, button_name)`. Logs and surfaces errors via `HomeAssistantError` so the UI shows them.

No polling. No state. `should_poll = False`.

### 4. `__init__.py`

Standard HA shape:
- `async_setup_entry`: build the API client (shared HA `httpx_client`), store it in `hass.data[DOMAIN][entry.entry_id]`, forward to the `button` platform.
- `async_unload_entry`: unload platforms, drop the client from `hass.data`.
- `async_reload_entry`: on options update.

### 5. `manifest.json`

```json
{
  "domain": "switchbot_ir_others",
  "name": "SwitchBot IR (Others)",
  "version": "0.1.0",
  "documentation": "https://github.com/<owner>/ha-switchbot-ir-others",
  "issue_tracker": "https://github.com/<owner>/ha-switchbot-ir-others/issues",
  "codeowners": ["@<owner>"],
  "config_flow": true,
  "iot_class": "cloud_push",
  "integration_type": "hub",
  "requirements": []
}
```

`iot_class: cloud_push` because all calls go through SwitchBot's cloud. No external requirements — `httpx` ships with HA core.

### 6. `hacs.json`

```json
{
  "name": "SwitchBot IR (Others)",
  "homeassistant": "2024.10.0",
  "render_readme": true
}
```

## Data flow: pressing a button

```
User clicks button.office_ac_temp_up in HA
  └─► SwitchbotIROthersButton.async_press()
       └─► SwitchBotApiClient.send_command(device_id="01-...", command="TEMP UP")
            ├─ Build t, nonce, sign
            ├─ POST https://api.switch-bot.com/v1.1/devices/01-.../commands
            │       body: {"commandType":"customize","command":"TEMP UP","parameter":"default"}
            └─ Parse response: statusCode=100 → success; else raise
       └─► SwitchBot Hub emits IR pulse → AC responds
```

## Error handling

| Failure | Surface |
|---|---|
| Invalid token/secret at setup | Config flow form error: "Invalid credentials" |
| Network down at setup | Config flow form error: "Cannot connect" |
| Zero "Others" remotes returned | Config flow abort reason: `no_others_remotes` |
| Button press, network down | `HomeAssistantError` → toast in UI; entity stays available |
| Button press, auth expired | `SwitchBotAuthError` → trigger reauth flow; entity goes unavailable until resolved |
| Button name not recognised by SwitchBot (user typo) | API returns `statusCode != 100`; `HomeAssistantError` with the returned message |
| Rate limit (10000 calls/day) | API returns `statusCode 190` per docs; raise `HomeAssistantError` with explicit "rate limit" message |

## Testing strategy

Tests live in `tests/` and use `pytest` + `pytest-homeassistant-custom-component`.

- **API client unit tests** (`tests/test_api.py`):
  - Signing produces a deterministic `sign` value for known `token/secret/t/nonce` inputs (golden test).
  - `send_command` builds the correct URL, body, and headers (httpx mock).
  - Non-2xx and `statusCode != 100` both raise.
- **Config flow tests** (`tests/test_config_flow.py`):
  - Happy path: user → select_remotes → buttons (x N) → entry created with expected `data` and `options`.
  - Invalid auth on step 1 → form re-displayed with error.
  - Zero "Others" remotes → abort.
  - Options flow round-trips edited button lists.
- **Button platform test** (`tests/test_button.py`):
  - Setting up an entry creates one entity per (remote × button).
  - `async_press` calls the API client with the right `device_id` and `command`.
  - All buttons for a remote share one `device_info` group.

CI: GitHub Actions running `pytest` + `ruff` on every push.

## Project layout

```
ha-switchbot-ir-others/
├── custom_components/
│   └── switchbot_ir_others/
│       ├── __init__.py
│       ├── api.py
│       ├── button.py
│       ├── config_flow.py
│       ├── const.py
│       ├── manifest.json
│       └── strings.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_button.py
│   └── test_config_flow.py
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-21-switchbot-ir-others-design.md
├── .github/
│   └── workflows/
│       └── ci.yml
├── hacs.json
├── README.md
├── LICENSE
└── pyproject.toml
```

## Open questions to resolve during implementation

1. **`remoteType` filter value.** What does the SwitchBot v1.1 `GET /v1.1/devices` response actually return for learned "Others" remotes — `"Others"`, `"DIY"`, or `""`? Resolve by inspecting the real response for the user's OFFICE AC; widen the filter if needed.
2. **Button slug collisions.** If two buttons slugify to the same value (e.g. `TEMP UP` and `TEMP-UP`), append an index. Decide policy when first encountered.
3. **Whether `parameter` must always be `"default"`.** SwitchBot docs say `default` for `customize` command type. If a real remote rejects it, switch to omitting the field.
