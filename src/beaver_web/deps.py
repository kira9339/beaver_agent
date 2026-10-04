"""Shared application state (BeaverCoreClient + session manager) for the web layer."""

from __future__ import annotations

from typing import Optional

_client = None
_manager = None


def init_app_state(client, manager) -> None:
    global _client, _manager
    _client = client
    _manager = manager


def reload_client():
    """Rebuild ``BeaverCoreClient`` from the config on disk and re-point everything.

    The settings page writes ``~/.beaver/config.yaml``; without this the running
    server (and every open session) would keep using the old provider.
    """
    from beaver_client import BeaverConfig, BeaverCoreClient

    global _client
    client = BeaverCoreClient(BeaverConfig())
    _client = client
    if _manager is not None:
        _manager.swap_client(client)
    return client


def get_client():
    if _client is None:
        raise RuntimeError("app state not initialized")
    return _client


def get_manager():
    if _manager is None:
        raise RuntimeError("app state not initialized")
    return _manager
