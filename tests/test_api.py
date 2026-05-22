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
    SwitchBotRateLimitError,
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


def test_rate_limit_error_is_api_error() -> None:
    assert issubclass(SwitchBotRateLimitError, SwitchBotApiError)


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
async def test_send_command_posts_customize_and_signs() -> None:
    captured: dict[str, Any] = {}

    def _record(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["url"] = str(request.url)
        captured["body"] = _json.loads(request.content)
        captured["sign"] = request.headers.get("sign")
        captured["auth"] = request.headers.get("Authorization")
        captured["t"] = request.headers.get("t")
        captured["nonce"] = request.headers.get("nonce")
        return httpx.Response(
            200, json={"statusCode": 100, "message": "ok", "body": {}}
        )

    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/dev-1/commands").mock(
                side_effect=_record
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            await client.send_command("dev-1", "TEMP UP")

    assert captured["url"].endswith("/devices/dev-1/commands")
    assert captured["body"] == {
        "commandType": "customize",
        "command": "TEMP UP",
        "parameter": "default",
    }
    # SwitchBot v1.1 expects the raw token in Authorization (no "Bearer" prefix).
    assert captured["auth"] == "tk"
    assert captured["sign"]
    assert captured["t"]
    assert captured["nonce"]


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
                    200,
                    json={
                        "statusCode": 161,
                        "message": "Token invalid",
                        "body": {},
                    },
                )
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotAuthError):
                await client.send_command("d", "X")


@pytest.mark.asyncio
async def test_send_command_raises_auth_on_status_171() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "statusCode": 171,
                        "message": "Hub device offline",
                        "body": {},
                    },
                )
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotAuthError):
                await client.send_command("d", "X")


@pytest.mark.asyncio
async def test_send_command_raises_rate_limit_on_status_190() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "statusCode": 190,
                        "message": "Rate limited",
                        "body": {},
                    },
                )
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotRateLimitError) as info:
                await client.send_command("d", "X")
            assert "190" in str(info.value)


@pytest.mark.asyncio
async def test_send_command_raises_rate_limit_on_http_429() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(429, text="Too Many Requests")
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotRateLimitError):
                await client.send_command("d", "X")


@pytest.mark.asyncio
async def test_send_command_raises_api_error_on_other_status() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.post(f"{API_BASE_URL}/devices/d/commands").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "statusCode": 151,
                        "message": "Device not found",
                        "body": {},
                    },
                )
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotApiError) as info:
                await client.send_command("d", "X")
            assert not isinstance(info.value, SwitchBotAuthError)
            assert not isinstance(info.value, SwitchBotRateLimitError)
            assert "151" in str(info.value)


@pytest.mark.asyncio
async def test_request_handles_non_json_body() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.get(f"{API_BASE_URL}/devices").mock(
                return_value=httpx.Response(200, text="<html>oops</html>")
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotApiError, match="Non-JSON response"):
                await client.list_infrared_remotes()


@pytest.mark.asyncio
async def test_request_handles_network_error() -> None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.get(f"{API_BASE_URL}/devices").mock(
                side_effect=httpx.ConnectError("connection refused")
            )
            client = SwitchBotApiClient(token="tk", secret="sk", http_client=http)
            with pytest.raises(SwitchBotApiError, match="Network error"):
                await client.list_infrared_remotes()
