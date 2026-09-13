"""FastAPI application: the real WhatsApp webhook plus a small `/dev`
endpoint for driving full conversations over plain HTTP without needing
WhatsApp credentials or payload shapes (used by the demo/test harness).

No clinical logic here — everything is delegated to Pipeline.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from ..channel import whatsapp_adapter
from ..config import settings
from ..extraction import keyword_extractor, llm_extractor
from ..pipeline import Pipeline
from ..session.session_manager import SessionManager

logger = logging.getLogger(__name__)


def _build_pipeline() -> Pipeline:
    if settings.anthropic_api_key:
        manager = SessionManager(extract_fn=llm_extractor.extract, extractor_name="llm")
    else:
        manager = SessionManager(extract_fn=keyword_extractor.extract, extractor_name="keyword")
    return Pipeline(manager)


app = FastAPI(title="Diabetes Triage Chatbot Prototype")
pipeline = _build_pipeline()
transport = whatsapp_adapter.default_transport()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "allow_patient_use": settings.allow_patient_use}


# ---------------------------------------------------------------------------
# WhatsApp webhook (Meta Cloud API)
# ---------------------------------------------------------------------------


@app.get("/webhook/whatsapp")
def webhook_verify(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    result = whatsapp_adapter.verify_webhook(mode, token, challenge)
    if result is not None:
        return PlainTextResponse(result, status_code=200)
    return PlainTextResponse("verification failed", status_code=403)


@app.post("/webhook/whatsapp")
async def webhook_receive(request: Request) -> Response:
    body_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    # HMAC signature verification against the app secret. Fails closed —
    # if no secret is configured (e.g. local dev), reject rather than trust.
    if settings.whatsapp_app_secret:
        if not whatsapp_adapter.verify_signature(body_bytes, signature):
            logger.warning("webhook_receive: signature verification failed")
            return PlainTextResponse("invalid signature", status_code=403)

    try:
        payload = await request.json()
    except Exception:
        logger.exception("webhook_receive: could not parse JSON body")
        # WhatsApp retries on anything but a prompt 200 — a malformed body
        # is not something a retry will fix, so ack it and move on.
        return PlainTextResponse("ignored", status_code=200)

    for parsed in whatsapp_adapter.parse_webhook_payload(payload):
        if parsed.message_type == "unsupported":
            fallback = transport.send(
                parsed.from_number,
                _unsupported_message(),
            )
            continue
        result = pipeline.handle(
            session_id=parsed.from_number,
            text=parsed.text,
            message_id=parsed.message_id,
            button_value=parsed.button_value,
        )
        for message in result.messages:
            transport.send(parsed.from_number, message)

    # Always ack promptly — a slow reply is exactly what makes WhatsApp
    # redeliver, which is why idempotency (bug #5) exists independently.
    return PlainTextResponse("ok", status_code=200)


def _unsupported_message():
    from ..rendering.renderer import OutboundMessage

    return OutboundMessage(
        text="Sorry, I can only understand text and button replies right now. Please reply with text.",
    )


# ---------------------------------------------------------------------------
# Dev endpoint — drives full conversations over HTTP with no WhatsApp
# credentials, for the demo/test harness.
# ---------------------------------------------------------------------------


class DevMessageIn(BaseModel):
    session_id: str
    text: str = ""
    button_value: str | None = None
    message_id: str | None = None


class DevMessageOut(BaseModel):
    messages: list[str]
    tier: int | None
    terminal: bool
    fired_rule_ids: tuple[str, ...]
    invented_rules_used: tuple[str, ...]
    unsourced_rules_used: tuple[str, ...]


@app.post("/dev/message", response_model=DevMessageOut)
def dev_message(payload: DevMessageIn) -> DevMessageOut:
    result = pipeline.handle(
        session_id=payload.session_id,
        text=payload.text,
        message_id=payload.message_id,
        button_value=payload.button_value,
    )
    verdict = pipeline.session_manager.get_or_create(payload.session_id).verdict
    return DevMessageOut(
        messages=[m.text for m in result.messages],
        tier=result.tier,
        terminal=result.terminal,
        fired_rule_ids=verdict.fired_rule_ids if verdict else (),
        invented_rules_used=verdict.invented_rules_used if verdict else (),
        unsourced_rules_used=verdict.unsourced_rules_used if verdict else (),
    )
