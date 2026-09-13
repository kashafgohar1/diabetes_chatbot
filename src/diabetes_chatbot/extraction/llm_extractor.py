"""LLM-backed extractor: natural language -> strict-JSON clinical slots.

This is the ONLY module in the pipeline allowed to call an LLM. It never
sees a tier and never decides anything — it fills the same slot vocabulary
the keyword extractor fills (extraction/schema.py), nothing more.

Fails closed: on any error, timeout, missing credentials, or unparseable
output, it returns {} (nothing learned). Slots stay UNKNOWN and the engine
asks again — it never assumes an answer the model didn't clearly give.
"""

from __future__ import annotations

import json
import logging

from ..config import settings
from ..state import TriState
from .schema import EXTRACTION_JSON_SCHEMA, TRISTATE_SLOTS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You extract structured clinical slots from a short WhatsApp \
message in a diabetes triage conversation. You are NOT diagnosing and NOT \
deciding urgency — you only translate natural language into fixed fields.

Rules:
- Only set a field if the message clearly states it. If it is not mentioned \
or is ambiguous, omit the field entirely — never guess.
- Tri-state fields take "yes", "no", or "unknown" — use "unknown" only if \
the message explicitly says the person doesn't know; otherwise omit the \
field rather than guessing.
- glucose_value/glucose_unit: only set these if a numeric blood glucose \
reading is stated. If a number is given with no unit, set glucose_value \
and leave glucose_unit null — never guess mg/dL vs mmol/L.
- insulin_dose_request_detected: true only if the message is asking how \
much insulin/medication to take, in any framing.
- Never include any field not in the schema. Never include a tier, a rule \
ID, a diagnosis, or a dose recommendation — that is not your job."""


def _client():
    import anthropic  # local import: keeps this dependency confined to the
    # extraction package, never reachable from the decision engine.

    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=8.0, max_retries=1)


def extract(text: str, pending_slot: str | None = None) -> dict:
    """Best-effort LLM extraction. Returns {} on any failure (fail-closed)."""
    client = _client()
    if client is None:
        logger.info("llm_extractor: no ANTHROPIC_API_KEY configured, skipping (fail-closed)")
        return {}

    user_prompt = text
    if pending_slot:
        user_prompt = f"[The question just asked was about: {pending_slot}]\n{text}"

    try:
        response = client.messages.create(
            model=settings.llm_extraction_model,
            max_tokens=512,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"format": {"type": "json_schema", "schema": EXTRACTION_JSON_SCHEMA}},
        )
    except Exception:  # noqa: BLE001 — fail closed on ANY error, deliberately broad
        logger.exception("llm_extractor: request failed, failing closed")
        return {}

    try:
        text_block = next(b.text for b in response.content if b.type == "text")
        raw = json.loads(text_block)
    except Exception:  # noqa: BLE001 — unparseable output must not propagate
        logger.exception("llm_extractor: unparseable response, failing closed")
        return {}

    return _sanitize(raw)


def _sanitize(raw: dict) -> dict:
    """Defence in depth: even though output_config.format constrains the
    model, never trust a network response blindly. Drop anything outside
    the known schema/enum before it reaches clinical state.
    """
    updates: dict = {}
    if not isinstance(raw, dict):
        return {}

    for slot in TRISTATE_SLOTS:
        value = raw.get(slot)
        if value in ("yes", "no", "unknown"):
            updates[slot] = TriState(value)

    glucose_value = raw.get("glucose_value")
    if isinstance(glucose_value, (int, float)):
        updates["glucose_value"] = float(glucose_value)
        unit = raw.get("glucose_unit")
        if unit in ("mg/dL", "mmol/L"):
            updates["glucose_unit"] = unit
            updates["glucose_unit_ambiguous"] = False
        else:
            updates["glucose_unit"] = None
            updates["glucose_unit_ambiguous"] = True

    if raw.get("insulin_dose_request_detected") is True:
        updates["insulin_dose_request_detected"] = True

    return updates
