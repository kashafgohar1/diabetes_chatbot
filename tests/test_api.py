"""In-process HTTP tests for the FastAPI app: the dev endpoint (used to
drive full conversations without WhatsApp credentials) and the webhook
verification handshake + HMAC signature enforcement.

See tests/test_http_live.py for the same webhook driven over a REAL socket
against a booted uvicorn server, not just an in-process test client.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from diabetes_chatbot.api import app as app_module
from diabetes_chatbot.channel import whatsapp_adapter

client = TestClient(app_module.app)


def sid() -> str:
    return f"api-test-{uuid.uuid4().hex[:8]}"


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["allow_patient_use"] is False


def test_dev_message_full_conversation_reaches_tier1():
    session_id = sid()
    r = client.post("/dev/message", json={"session_id": session_id, "text": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["terminal"] is False

    # consent, age, role, unconscious, non-diabetes-emergency, pregnant,
    # presenting_complaint, swallow-safely, self-treat-unaided,
    # frequent/impaired-awareness, mild-symptoms -> Tier 1 (rule A1).
    button_sequence = [
        "yes", "yes", "patient", "no", "no", "no", "hypo", "yes", "yes", "no", "yes",
    ]
    for value in button_sequence:
        r = client.post("/dev/message", json={"session_id": session_id, "text": "", "button_value": value})
        assert r.status_code == 200

    body = r.json()
    assert body["terminal"] is True
    assert body["tier"] == 1
    assert "A1" in body["fired_rule_ids"]


def test_dev_message_caregiver_unresponsive_immediate_tier3():
    session_id = sid()
    r = client.post(
        "/dev/message",
        json={"session_id": session_id, "text": "my father is not responding normally"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["terminal"] is True
    assert body["tier"] == 3
    assert "G1" in body["fired_rule_ids"]


def test_webhook_verification_handshake_returns_challenge():
    from diabetes_chatbot.config import settings

    settings.whatsapp_verify_token = "test-verify-token"
    try:
        r = client.get(
            "/webhook/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "12345"},
        )
        assert r.status_code == 200
        assert r.text == "12345"
    finally:
        settings.whatsapp_verify_token = None


def test_webhook_verification_handshake_rejects_wrong_token():
    from diabetes_chatbot.config import settings

    settings.whatsapp_verify_token = "test-verify-token"
    try:
        r = client.get(
            "/webhook/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "12345"},
        )
        assert r.status_code == 403
    finally:
        settings.whatsapp_verify_token = None


def _wa_text_payload(from_number: str, text: str, message_id: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": from_number, "id": message_id, "type": "text", "text": {"body": text}}
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_webhook_rejects_invalid_hmac_signature():
    from diabetes_chatbot.config import settings

    settings.whatsapp_app_secret = "test-app-secret"
    try:
        payload = _wa_text_payload("15551234567", "hi", "wamid.1")
        body_bytes = json.dumps(payload).encode()
        r = client.post(
            "/webhook/whatsapp",
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
        )
        assert r.status_code == 403
    finally:
        settings.whatsapp_app_secret = None


def test_webhook_accepts_valid_hmac_signature_and_returns_200():
    from diabetes_chatbot.config import settings

    settings.whatsapp_app_secret = "test-app-secret"
    try:
        payload = _wa_text_payload("15551234568", "hi", "wamid.2")
        body_bytes = json.dumps(payload).encode()
        signature = hmac.new(b"test-app-secret", body_bytes, hashlib.sha256).hexdigest()
        r = client.post(
            "/webhook/whatsapp",
            content=body_bytes,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={signature}"},
        )
        assert r.status_code == 200
    finally:
        settings.whatsapp_app_secret = None


def test_webhook_handles_unsupported_message_type_gracefully():
    payload = {
        "entry": [
            {
                "changes": [
                    {"value": {"messages": [{"from": "15550000000", "id": "wamid.3", "type": "image"}]}}
                ]
            }
        ]
    }
    r = client.post("/webhook/whatsapp", json=payload)
    assert r.status_code == 200
