"""WhatsApp (Meta Cloud API) adapter. Deliberately thin — NO clinical logic
here, only: verification handshake, HMAC signature verification, parsing
inbound webhook payloads into plain (text, message_id, button_value)
tuples, and sending text/interactive-button replies. This boundary is what
lets the channel be swapped for SMS or a web widget without touching the
pipeline.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass, field

import httpx

from ..config import settings
from ..rendering.renderer import OutboundMessage

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"


@dataclass(frozen=True)
class ParsedMessage:
    from_number: str
    message_id: str | None
    text: str
    button_value: str | None
    message_type: str  # "text" | "interactive" | "unsupported"


def verify_webhook(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    """GET /webhook verification handshake. Returns the challenge string to
    echo back on success, or None if verification fails.
    """
    if mode == "subscribe" and token is not None and settings.whatsapp_verify_token is not None:
        if hmac.compare_digest(token, settings.whatsapp_verify_token):
            return challenge
    return None


def verify_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """Verifies X-Hub-Signature-256 against the configured app secret.
    Fails closed: no app secret configured, no header, or mismatch -> False.
    """
    if not settings.whatsapp_app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def parse_webhook_payload(payload: dict) -> list[ParsedMessage]:
    """Parses a Meta Cloud API webhook body into ParsedMessage objects.
    Unsupported message types (image, audio, location, ...) are returned
    with message_type="unsupported" and empty text — the pipeline handles
    them gracefully rather than crashing.
    """
    parsed: list[ParsedMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                parsed.append(_parse_one(message))
    return parsed


def _parse_one(message: dict) -> ParsedMessage:
    from_number = message.get("from", "")
    message_id = message.get("id")
    msg_type = message.get("type", "unsupported")

    if msg_type == "text":
        return ParsedMessage(from_number, message_id, message.get("text", {}).get("body", ""), None, "text")

    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        if "button_reply" in interactive:
            reply = interactive["button_reply"]
            return ParsedMessage(from_number, message_id, reply.get("title", ""), reply.get("id"), "interactive")
        if "list_reply" in interactive:
            reply = interactive["list_reply"]
            return ParsedMessage(from_number, message_id, reply.get("title", ""), reply.get("id"), "interactive")
        return ParsedMessage(from_number, message_id, "", None, "unsupported")

    if msg_type == "button":
        # Legacy quick-reply button format
        btn = message.get("button", {})
        return ParsedMessage(from_number, message_id, btn.get("text", ""), btn.get("payload"), "interactive")

    return ParsedMessage(from_number, message_id, "", None, "unsupported")


class Transport:
    """Abstract send transport. NullTransport (default, no credentials) just
    records what would have been sent — this is what lets the demo and
    tests exercise the full adapter without real WhatsApp credentials.
    """

    def send(self, to: str, message: OutboundMessage) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


class NullTransport(Transport):
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, message: OutboundMessage) -> dict:
        record = {"to": to, "text": message.text, "buttons": message.buttons, "dry_run": True}
        self.sent.append(record)
        logger.info("NullTransport (dry-run) send to %s: %s", to, message.text[:80])
        return record


class GraphAPITransport(Transport):
    def __init__(self, access_token: str, phone_number_id: str, timeout: float = 10.0):
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.timeout = timeout

    def _url(self) -> str:
        return f"https://graph.facebook.com/{GRAPH_API_VERSION}/{self.phone_number_id}/messages"

    def send(self, to: str, message: OutboundMessage) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if message.buttons:
            body = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": message.text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": value, "title": label[:20]}}
                            for label, value in message.buttons[:3]  # WhatsApp caps at 3 buttons
                        ]
                    },
                },
            }
        else:
            body = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": message.text},
            }
        response = httpx.post(self._url(), json=body, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


def default_transport() -> Transport:
    if settings.whatsapp_access_token and settings.whatsapp_phone_number_id:
        return GraphAPITransport(settings.whatsapp_access_token, settings.whatsapp_phone_number_id)
    return NullTransport()
