"""SwitchBot Cloud API client for the IR Others integration."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

import httpx

from .const import (
    API_BASE_URL,
    API_STATUS_OK,
    API_STATUS_RATE_LIMITED,
    API_STATUS_UNAUTHORIZED,
    API_TIMEOUT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def _build_signature(*, token: str, secret: str, t: str, nonce: str) -> str:
    """Build the SwitchBot v1.1 'sign' header value.

    Algorithm: base64(HMAC_SHA256(secret, token + t + nonce)).upper()
    """
    string_to_sign = (token + t + nonce).encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii").upper()


class SwitchBotApiError(Exception):
    """Raised when the SwitchBot API returns an error or is unreachable."""


class SwitchBotAuthError(SwitchBotApiError):
    """Raised when SwitchBot rejects the token/secret."""


class SwitchBotRateLimitError(SwitchBotApiError):
    """Raised when SwitchBot returns a rate-limit response."""


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
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{API_BASE_URL}{path}"
        headers = self._build_headers()
        _LOGGER.debug("SwitchBot API %s %s", method, path)
        try:
            resp = await self._http.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=API_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            raise SwitchBotApiError(f"Network error: {exc}") from exc

        if resp.status_code in (401, 403):
            raise SwitchBotAuthError(f"HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise SwitchBotRateLimitError(f"HTTP 429: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise SwitchBotApiError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise SwitchBotApiError(
                f"Non-JSON response from SwitchBot: {resp.text[:200]}"
            ) from exc

        status_code = data.get("statusCode")
        if status_code != API_STATUS_OK:
            message = data.get("message", "unknown error")
            if status_code in API_STATUS_UNAUTHORIZED:
                raise SwitchBotAuthError(f"SwitchBot {status_code}: {message}")
            if status_code in API_STATUS_RATE_LIMITED:
                raise SwitchBotRateLimitError(f"SwitchBot {status_code}: {message}")
            raise SwitchBotApiError(f"SwitchBot {status_code}: {message}")
        return data.get("body") or {}

    async def list_infrared_remotes(self) -> list[dict[str, Any]]:
        body = await self._request("GET", "/devices")
        return body.get("infraredRemoteList", [])

    async def send_command(self, device_id: str, command: str) -> None:
        _LOGGER.debug("Sending command %r to device %s", command, device_id)
        await self._request(
            "POST",
            f"/devices/{device_id}/commands",
            json_body={
                "commandType": "customize",
                "command": command,
                "parameter": "default",
            },
        )
