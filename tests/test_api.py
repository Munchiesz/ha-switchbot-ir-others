"""Tests for the SwitchBot API client."""

from __future__ import annotations

from typing import Any

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
