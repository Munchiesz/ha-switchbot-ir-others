"""Shared pytest fixtures."""

from __future__ import annotations

import socket as _socket
import sys

import pytest


if sys.platform == "win32":
    # On Windows, asyncio.ProactorEventLoop uses _fallback_socketpair (AF_INET)
    # for its internal self-pipe. pytest-homeassistant-custom-component replaces
    # socket.socket with a GuardedSocket that blocks AF_INET __new__, which makes
    # the event loop impossible to create. We patch socketpair to use the real
    # socket.socket so the event loop self-pipe always works regardless of whether
    # pytest-socket has replaced socket.socket.
    import pytest_socket as _pytest_socket
    _real_socket = _pytest_socket._true_socket  # the original socket.socket, saved by pytest-socket

    def _win32_socketpair(family=_socket.AF_INET, type=_socket.SOCK_STREAM, proto=0):  # noqa: A002
        """socketpair that always uses the real socket.socket (not GuardedSocket).

        This is needed because Windows has no native socketpair() and Python's
        _fallback_socketpair uses socket.socket which may have been replaced by
        pytest-socket's GuardedSocket that blocks AF_INET creation. We also need
        to temporarily restore the real socket.socket so that lsock.accept() (which
        internally calls socket.socket(fileno=fd)) uses the unguarded implementation.
        """
        if family == _socket.AF_INET:
            host = "127.0.0.1"
        elif family == _socket.AF_INET6:
            host = "::1"
        else:
            raise ValueError("Only AF_INET and AF_INET6 socket address families are supported")
        if type != _socket.SOCK_STREAM:
            raise ValueError("Only SOCK_STREAM socket type is supported")
        if proto != 0:
            raise ValueError("Only protocol zero is supported")
        # Temporarily restore the real socket.socket so accept() works
        guarded = _socket.socket
        _socket.socket = _real_socket
        try:
            lsock = _real_socket(family, type, proto)
            try:
                lsock.bind((host, 0))
                lsock.listen()
                addr, port = lsock.getsockname()[:2]
                csock = _real_socket(family, type, proto)
                try:
                    csock.setblocking(False)
                    try:
                        csock.connect((addr, port))
                    except (BlockingIOError, InterruptedError):
                        pass
                    csock.setblocking(True)
                    ssock, _ = lsock.accept()
                except Exception:
                    csock.close()
                    raise
            finally:
                lsock.close()
        finally:
            _socket.socket = guarded
        return (ssock, csock)

    _socket.socketpair = _win32_socketpair  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    yield
