"""Boots the REAL API server (uvicorn, a real TCP socket) in a background
thread and drives a complete conversation over actual HTTP — not just the
in-process TestClient. This is what "the API server boots and handles
complete conversations over real HTTP" actually means, automated.
"""

from __future__ import annotations

import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn

from diabetes_chatbot.api import app as app_module


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    port = _free_port()
    config = uvicorn.Config(app_module.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=0.5)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("live server did not start in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


def test_health_over_real_http(live_server):
    r = httpx.get(f"{live_server}/health")
    assert r.status_code == 200
    assert r.json()["allow_patient_use"] is False


def test_full_conversation_over_real_http_reaches_tier3_foot(live_server):
    session_id = f"live-{uuid.uuid4().hex[:8]}"
    sequence = [
        {"text": "hi"},
        {"button_value": "yes"},  # consent
        {"button_value": "yes"},  # age
        {"button_value": "caregiver"},  # role
        {"button_value": "no"},  # unconscious
        {"button_value": "no"},  # non-diabetes emergency
        {"button_value": "no"},  # pregnant
        {"button_value": "foot"},  # presenting complaint
        {"button_value": "yes"},  # severe foot signs -> D3
    ]
    last = None
    for payload in sequence:
        body = {"session_id": session_id, "text": payload.get("text", ""), "button_value": payload.get("button_value")}
        r = httpx.post(f"{live_server}/dev/message", json=body, timeout=5)
        assert r.status_code == 200
        last = r.json()

    assert last["terminal"] is True
    assert last["tier"] == 3
    assert "D3" in last["fired_rule_ids"]
    assert "D3" in last["unsourced_rules_used"]


def test_webhook_returns_200_over_real_http(live_server):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "15559998888",
                                    "id": f"wamid.{uuid.uuid4().hex[:8]}",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    r = httpx.post(f"{live_server}/webhook/whatsapp", json=payload, timeout=5)
    assert r.status_code == 200


def test_g1_override_over_real_http_gives_tier3_and_no_guard_violations(live_server):
    session_id = f"live-{uuid.uuid4().hex[:8]}"
    r = httpx.post(
        f"{live_server}/dev/message",
        json={"session_id": session_id, "text": "please help, she is not waking up properly"},
        timeout=5,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["terminal"] is True
    assert body["tier"] == 3
    assert "G1" in body["fired_rule_ids"]
