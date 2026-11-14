"""WebSocket hardening: origin check and per-IP connection cap (no Redis needed)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import ws as ws_module
from app.core.config import settings


def test_rejects_foreign_origin_when_origins_configured(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://p2p.example.org")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as s:
            s.receive_json()
    with client.websocket_connect("/ws", headers={"origin": "https://p2p.example.org"}) as s:
        assert s.receive_json() == {"subscribed": ["interval", "price", "trades"]}


def test_per_ip_cap(client: TestClient, monkeypatch):
    monkeypatch.setattr(ws_module, "MAX_WS_PER_IP", 2)
    a = client.websocket_connect("/ws").__enter__()
    b = client.websocket_connect("/ws").__enter__()
    try:
        assert a.receive_json()["subscribed"] and b.receive_json()["subscribed"]
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as c:
                c.receive_json()
    finally:
        a.__exit__(None, None, None)
        b.__exit__(None, None, None)
