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
