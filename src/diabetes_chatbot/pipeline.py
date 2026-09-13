"""Wires the layers together for one turn:

inbound text -> [session manager: redflags -> extraction -> engine -> render]
             -> output guardrail (per message)
             -> audit log (both directions)
             -> outbound messages

This is the module channel adapters (WhatsApp, CLI, the dev HTTP endpoint)
call. It owns no clinical logic itself — that all lives in session_manager
and engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from .audit.audit_log import AuditLog, default_log
from .guardrail import output_guardrail
from .rendering.renderer import OutboundMessage
from .session.session_manager import SessionManager


@dataclass
class PipelineTurnResult:
    messages: list[OutboundMessage]
    tier: int | None
    terminal: bool


class Pipeline:
    def __init__(self, session_manager: SessionManager, audit_log: AuditLog | None = None):
        self.session_manager = session_manager
        self.audit_log = audit_log or default_log

    def handle(
        self,
        session_id: str,
        text: str,
        message_id: str | None = None,
        button_value: str | None = None,
    ) -> PipelineTurnResult:
        session = self.session_manager.get_or_create(session_id)
        phase_before = session.pending_slot or ("terminal" if session.terminal else "unknown")

        outcome = self.session_manager.process_turn(
            session_id, text, message_id=message_id, button_value=button_value
        )

        self.audit_log.record(
            session_id=session_id,
            direction="inbound",
            turn=session.turn_count,
            message_id=message_id,
            text=text,
            phase=phase_before,
            tier=None,
            fired_rule_ids=(),
            invented_rules_used=(),
            unsourced_rules_used=(),
            guard_violations=(),
            guard_passed=True,
            extractor_used=self.session_manager.extractor_name,
        )

        final_messages: list[OutboundMessage] = []
        for message in outcome.messages:
            tier_for_check = outcome.tier if message.kind == "verdict" else None
            guard_result = output_guardrail.evaluate(message.text, tier_for_check)

            if guard_result.passed:
                final_messages.append(message)
                sent_text = message.text
            else:
                from .rendering import renderer as _renderer

                fallback = _renderer.render_guardrail_fallback()
                final_messages.append(fallback)
                sent_text = fallback.text

            self.audit_log.record(
                session_id=session_id,
                direction="outbound",
                turn=session.turn_count,
                message_id=None,
                text=sent_text,
                phase=session.pending_slot or ("terminal" if session.terminal else "unknown"),
                tier=outcome.tier if message.kind == "verdict" else None,
                fired_rule_ids=outcome.fired_rule_ids if message.kind == "verdict" else (),
                invented_rules_used=outcome.invented_rules_used if message.kind == "verdict" else (),
                unsourced_rules_used=outcome.unsourced_rules_used if message.kind == "verdict" else (),
                guard_violations=guard_result.violations,
                guard_passed=guard_result.passed,
                extractor_used=self.session_manager.extractor_name,
                note="" if guard_result.passed else f"DISCARDED original message; violations={guard_result.violations}",
            )

        return PipelineTurnResult(messages=final_messages, tier=outcome.tier, terminal=outcome.terminal)
