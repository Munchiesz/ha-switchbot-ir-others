"""Tests for the SwitchBot API client."""

from __future__ import annotations

from custom_components.switchbot_ir_others.api import (
    SwitchBotApiError,
    SwitchBotAuthError,
    _build_signature,
)


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
