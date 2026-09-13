"""Renders approved content blocks into outbound messages.

An LLM, if enabled, may only rephrase the SURFACE WORDING of an already-
selected approved block (see `llm_rephrase`) — it is never given a tier,
never asked to author new content, and its output still passes through the
output guardrail like everything else. `ENABLE_LLM_REPHRASE` defaults to
False in this prototype: every message sent is the approved block verbatim
(plus the banner and any trigger list), which is the simplest way to
guarantee the "approved content blocks only" property for the demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..engine.types import NeedsInfo, Refusal, Verdict
from ..state import Role
from . import content_blocks as blocks

ENABLE_LLM_REPHRASE = False


@dataclass(frozen=True)
class OutboundMessage:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()
    kind: str = "text"


def llm_rephrase(text: str) -> str:
    """No-op unless ENABLE_LLM_REPHRASE is set. Documented extension point —
    see module docstring. Never called with tier/rule information.
    """
    if not ENABLE_LLM_REPHRASE:
        return text
    return text  # pragma: no cover - rephrase path not enabled in this prototype


def _with_banner(body: str) -> str:
    return f"{blocks.banner()}\n\n{body}"


def render_consent(role: Role | None) -> OutboundMessage:
    q = blocks.CONSENT_QUESTION
    return OutboundMessage(_with_banner(q.text_for(role)), q.buttons)


def render_consent_declined() -> OutboundMessage:
    return OutboundMessage(_with_banner(blocks.CONSENT_DECLINED_EXIT))


def render_age_question(role: Role | None) -> OutboundMessage:
    q = blocks.AGE_QUESTION
    return OutboundMessage(_with_banner(q.text_for(role)), q.buttons)


def render_under_18_exit() -> OutboundMessage:
    return OutboundMessage(_with_banner(blocks.UNDER_18_EXIT))


def render_role_question() -> OutboundMessage:
    q = blocks.ROLE_QUESTION
    return OutboundMessage(_with_banner(q.text_for(None)), q.buttons)


def render_presenting_complaint_question(role: Role | None) -> OutboundMessage:
    q = blocks.PRESENTING_COMPLAINT_QUESTION
    return OutboundMessage(_with_banner(llm_rephrase(q.text_for(role))), q.buttons)


def render_slot_question(slot: str, role: Role | None) -> OutboundMessage:
    q = blocks.QUESTION_BANK[slot]
    return OutboundMessage(_with_banner(llm_rephrase(q.text_for(role))), q.buttons)


def render_glucose_unit_clarify(role: Role | None) -> OutboundMessage:
    q = blocks.GLUCOSE_UNIT_CLARIFY
    return OutboundMessage(_with_banner(q.text_for(role)), q.buttons)


def render_needs_info(info: NeedsInfo, role: Role | None) -> OutboundMessage:
    if info.slot == "presenting_complaint":
        return render_presenting_complaint_question(role)
    return render_slot_question(info.slot, role)


def render_verdict(verdict: Verdict, role: Role | None) -> OutboundMessage:
    label = blocks.TIER_LABELS[verdict.tier]
    intro = blocks.TIER_INTROS[verdict.tier]
    trigger_list = blocks.DEFAULT_TRIGGER_LISTS[verdict.tier]
    body = f"{label}\n\n{intro}\n\n{trigger_list}"
    if verdict.unsourced_rules_used:
        body += blocks.UNSOURCED_NOTICE
    if verdict.safety_net:
        body += (
            " (This is a cautious default — none of the specific rules "
            "matched clearly, so we're erring on the side of getting this "
            "checked.)"
        )
    return OutboundMessage(_with_banner(llm_rephrase(body)), kind="verdict")


def render_refusal(refusal: Refusal, role: Role | None) -> OutboundMessage:
    if refusal.rule_id == "G2":
        return OutboundMessage(_with_banner(blocks.INSULIN_REFUSAL), kind="refusal")
    return OutboundMessage(_with_banner(blocks.GUARDRAIL_FALLBACK), kind="refusal")


def render_non_diabetes_emergency_exit() -> OutboundMessage:
    return OutboundMessage(_with_banner(blocks.NON_DIABETES_EMERGENCY_EXIT), kind="exit")


def render_pregnancy_exit() -> OutboundMessage:
    return OutboundMessage(_with_banner(blocks.PREGNANCY_EXIT), kind="exit")


def render_guardrail_fallback() -> OutboundMessage:
    return OutboundMessage(_with_banner(blocks.GUARDRAIL_FALLBACK), kind="guardrail_fallback")


def render_loop_escalation(role: Role | None) -> OutboundMessage:
    return OutboundMessage(_with_banner(blocks.LOOP_ESCALATION), kind="loop_escalation")
