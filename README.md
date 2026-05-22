# SwitchBot IR (Others) — Home Assistant integration

A HACS-installable custom integration that adds Home Assistant support for SwitchBot **"Others"-type** IR remotes — the user-learned remotes the official `switchbot_cloud` integration skips.

If you set up an AC, fan, or any other appliance under the "Others" category in the SwitchBot app and defined your own buttons (`ON/OFF`, `TEMP UP`, etc.), this integration surfaces each of those buttons as a `button` entity in Home Assistant.

## What it does

- Talks to the SwitchBot Cloud API (v1.1, HMAC-signed) — same auth as the official integration.
- Lists every `remoteType: "Others"` virtual remote on your account.
- Creates one `button` entity per user-defined button. Pressing the entity sends the IR command via your SwitchBot Hub.
- No polling, no state tracking. IR is one-way; this integration is a pure command passthrough.

## What it does NOT do

- It does not replace the official `switchbot_cloud` integration. Standard categories (AC, TV, Fan, Light) continue to be handled by the official integration. Run both side-by-side.
- It does not model a `climate` entity. Buttons map 1:1 to commands.
- It does not discover button names. The SwitchBot API does not expose them; you enter the list once during setup.

## Installation

### Via HACS (recommended)

1. HACS → Integrations → ••• → Custom repositories
2. Add `https://github.com/Munchiesz/ha-switchbot-ir-others` as an Integration
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

- **"Invalid token or secret"** — re-copy them from the SwitchBot app and paste them into the HA "Repair" / reauth prompt. If only the secret was rotated (not the token), reauth will pick up the new credentials and the existing entry keeps working.
- **Rotated the SwitchBot token itself?** A regenerated token registers as a different account inside this integration, so reauth will report `account_mismatch`. Remove the integration and re-add it with the new token.
- **"No 'Others'-type remotes were found"** — your account has no remotes set up under the Others category. Add one in the SwitchBot app first. If you set up the AC as a standard "Air Conditioner" type instead of "Others", this integration won't see it (by design — the official integration handles standard types).
- **Press succeeds but nothing happens** — the button name doesn't exactly match the SwitchBot app. Check capitalization, spaces, and slashes (e.g. `ON/OFF` not `on/off`).
- **Rate limited** — SwitchBot enforces 10,000 API calls per token per day. Be mindful in automations.

## Development

### Requirements

- Python 3.13+ (3.14 works locally)
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
git clone https://github.com/Munchiesz/ha-switchbot-ir-others
cd ha-switchbot-ir-others
uv pip install --system --group dev
```

### Running tests

```bash
python -m pytest tests/ -v
```

> **Windows note:** `pytest-homeassistant-custom-component` imports POSIX-only modules
> (`fcntl`, `resource`, `grp`, `pwd`, `termios`, `tty`) that don't exist on Windows.
> A `sitecustomize.py` stub is required to shadow these at import time. The CI pipeline
> uses `ubuntu-latest` so this is a dev-machine-only issue. Contact the maintainer
> for the stub if you develop on Windows.

### Linting

```bash
python -m ruff check custom_components tests
```

## License

MIT. See [LICENSE](LICENSE).
