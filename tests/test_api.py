"""Tests for the SwitchBot API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from custom_components.switchbot_ir_others.api import (
    SwitchBotApiClient,
    SwitchBotApiError,
    SwitchBotAuthError,
    _build_signature,
)
from custom_components.switchbot_ir_others.const import API_BASE_URL


def test_build_signature_matches_known_value() -> None:
    # Golden value computed via:
    # base64(HMAC_SHA256("sk", "tk" + "1700000000000" + "nonce-fixed")).upper()
    expected = "F8NITYLQ0+YNNM2R3IIPZGQW0WMOYFPXIKMJT6JOXFU="
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


def test_auth_error_is_api_error() -> None:
    assert issubclass(SwitchBotAuthError, SwitchBotApiError)


def test_api_error_carries_message() -> None:
    err = SwitchBotApiError("boom")
    assert str(err) == "boom"


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
