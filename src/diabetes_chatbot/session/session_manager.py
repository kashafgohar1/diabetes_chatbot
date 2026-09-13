"""Orchestrates one conversation: consent -> 18+ age gate -> patient-or-
caregiver role -> triage, driven turn-by-turn by the deterministic engine.

This module is the pipeline's brain but is itself still deterministic
except for the single call out to whichever extractor function it was
configured with (keyword-only by default; the LLM extractor is opt-in and
fails closed on its own — see extraction/llm_extractor.py). It never
imports an LLM client directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from .. import lexicon, redflags
from ..engine import engine
from ..engine.types import NeedsInfo, Refusal, Verdict
from ..extraction import keyword_extractor
from ..rendering import renderer
from ..rendering.renderer import OutboundMessage
from ..state import PresentingComplaint, Role, TriState
from .conversation import Session

ExtractFn = Callable[[str, Optional[str]], dict]

_VIRTUAL_SLOTS = {"consent", "age_over_18", "role", "presenting_complaint", "glucose_unit_clarify"}


def _guess_category(text: str) -> PresentingComplaint | None:
    t = text.lower()
    if any(w in t for w in ("shaky", "hungry", "sweaty", "low sugar", "hypo", "low blood sugar", "hypoglyc")):
        return PresentingComplaint.HYPOGLYCEMIA
    if any(w in t for w in ("high sugar", "high blood sugar", "dka", "ketones", "hyperglyc")):
        return PresentingComplaint.HYPERGLYCEMIA_DKA
    if any(w in t for w in ("foot", "toe", "wound", "ulcer", "sore on my")):
        return PresentingComplaint.FOOT
    if any(w in t for w in ("not diagnosed", "don't have diabetes", "undiagnosed", "never been diagnosed")):
        return PresentingComplaint.UNDIAGNOSED
    return None


@dataclass
class TurnOutcome:
    messages: list[OutboundMessage]
    tier: int | None
    fired_rule_ids: tuple[str, ...]
    invented_rules_used: tuple[str, ...]
    unsourced_rules_used: tuple[str, ...]
    terminal: bool


class SessionManager:
    def __init__(self, extract_fn: ExtractFn | None = None, extractor_name: str = "keyword"):
        self.sessions: dict[str, Session] = {}
        self.extract_fn = extract_fn or keyword_extractor.extract
        self.extractor_name = extractor_name

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(session_id=session_id)
        return self.sessions[session_id]

    # -- main entry point -----------------------------------------------

    def process_turn(
        self,
        session_id: str,
        raw_text: str,
        message_id: str | None = None,
        button_value: str | None = None,
    ) -> TurnOutcome:
        session = self.get_or_create(session_id)

        # Bug #5 fix: WhatsApp redelivers a message when it doesn't get a
        # prompt 200. A replayed message must be a complete no-op, not
        # re-applied to whichever slot happens to be pending next.
        if session.already_seen(message_id):
            return TurnOutcome([], session.verdict.tier if session.verdict else None, (), (), (), session.terminal)
        session.remember_message_id(message_id)
        session.turn_count += 1

        raw_text = raw_text or ""
        effective_text = button_value if button_value is not None else raw_text
        is_button = button_value is not None

        # Deterministic red-flag prefilter — raw text, every turn, before
        # any model call, regardless of session phase.
        redflags.apply(session.state, raw_text)

        messages: list[OutboundMessage] = []

        # G2: insulin/dose request can be asked at any point. Refuse
        # gracefully and keep going — never a dead end.
        if session.state.insulin_dose_request_detected:
            messages.append(renderer.render_refusal(Refusal("G2", "insulin/dose request"), session.state.role))
            session.state.insulin_dose_request_detected = False

        # G1/SN1/SN2 can fire at ANY point, including mid-consent-preamble,
        # from evidence the red-flag prefilter just found in raw text.
        override = engine.check_urgent_override(session.state)
        if override is not None:
            messages.append(self._finalize(session, override))
            return self._outcome(session, messages)

        # Loop detection (bug #4): keyed on (effective text, pending slot),
        # never on message text alone.
        if session.pending_slot is not None and not session.terminal:
            count = session.register_repeat(effective_text, session.pending_slot)
            if count >= 3:
                tier = max(session.last_needs_info_tier, 2)
                verdict = Verdict(
                    tier=tier,
                    fired_rule_ids=("LOOP_SAFETY",),
                    invented_rules_used=("LOOP_SAFETY",),
                    unsourced_rules_used=(),
                    safety_net=True,
                    reason="repeated non-answer to the same question — cautious escalation",
                )
                messages.append(renderer.render_loop_escalation(session.state.role))
                messages.append(self._finalize(session, verdict))
                return self._outcome(session, messages)

        if not session.terminal:
            self._apply_answer(session, effective_text, is_button)

        messages.append(self._advance(session))
        return self._outcome(session, messages)

    def _outcome(self, session: Session, messages: list[OutboundMessage]) -> TurnOutcome:
        verdict = session.verdict
        return TurnOutcome(
            messages=messages,
            tier=verdict.tier if verdict else None,
            fired_rule_ids=verdict.fired_rule_ids if verdict else (),
            invented_rules_used=verdict.invented_rules_used if verdict else (),
            unsourced_rules_used=verdict.unsourced_rules_used if verdict else (),
            terminal=session.terminal,
        )

    # -- applying an answer to whatever slot was pending -----------------

    def _apply_answer(self, session: Session, text: str, is_button: bool) -> None:
        slot = session.pending_slot
        if slot is None:
            return

        if slot == "consent":
            resolved = self._yes_no(text, is_button)
            if resolved is True:
                session.consent_given = True
            elif resolved is False:
                session.consent_declined = True
            return

        if slot == "age_over_18":
            resolved = self._yes_no(text, is_button)
            if resolved is True:
                session.state.age_over_18 = TriState.YES
            elif resolved is False:
                session.state.age_over_18 = TriState.NO
            return

        if slot == "role":
            if is_button and text in ("patient", "caregiver"):
                session.state.role = Role(text)
            else:
                detected = lexicon.detect_role(text)
                if detected is not None:
                    session.state.role = detected
            return

        if slot == "presenting_complaint":
            if is_button and text in (c.value for c in PresentingComplaint):
                session.state.presenting_complaint = PresentingComplaint(text)
            else:
                guess = _guess_category(text)
                if guess is not None:
                    session.state.presenting_complaint = guess
            return

        if slot == "glucose_unit_clarify":
            if is_button and text in ("mg/dL", "mmol/L"):
                session.state.glucose_unit = text
                session.state.glucose_unit_ambiguous = False
            elif is_button and text == "unknown":
                session.state.glucose_unit_ambiguous = False  # asked; patient doesn't know — stop asking
            else:
                _, unit, _ = lexicon.extract_glucose_reading(text)
                if unit is not None:
                    session.state.glucose_unit = unit
                    session.state.glucose_unit_ambiguous = False
                elif keyword_extractor.generic_tristate(text) is TriState.UNKNOWN:
                    session.state.glucose_unit_ambiguous = False
            return

        # A real clinical ClinicalState tri-state slot.
        if is_button and text in ("yes", "no", "unknown"):
            session.state.set(slot, TriState(text))
            return

        updates = self.extract_fn(text, slot)
        session.state.merge_known(updates)

    @staticmethod
    def _yes_no(text: str, is_button: bool) -> bool | None:
        if is_button:
            if text == "yes":
                return True
            if text == "no":
                return False
            return None
        result = keyword_extractor.generic_tristate(text)
        if result is TriState.YES:
            return True
        if result is TriState.NO:
            return False
        return None

    # -- driving the state machine forward --------------------------------

    def _advance(self, session: Session) -> OutboundMessage:
        if session.terminal and session.verdict is not None:
            # Nothing left to advance; re-send is not expected in normal
            # flow, but stay safe rather than crashing.
            return renderer.render_verdict(session.verdict, session.state.role)

        if not session.consent_given:
            if session.consent_declined:
                session.terminal = True
                session.pending_slot = None
                return renderer.render_consent_declined()
            session.pending_slot = "consent"
            return renderer.render_consent(session.state.role)

        if session.state.age_over_18 is TriState.NO:
            session.terminal = True
            session.pending_slot = None
            return renderer.render_under_18_exit()

        if session.state.age_over_18 is TriState.UNKNOWN:
            session.pending_slot = "age_over_18"
            return renderer.render_age_question(session.state.role)

        if session.state.role is None:
            session.pending_slot = "role"
            return renderer.render_role_question()

        # OQ-8: a bare glucose number with no unit interrupts the flow with
        # a clarifying question rather than ever guessing mg/dL vs mmol/L.
        if session.state.glucose_unit_ambiguous:
            session.pending_slot = "glucose_unit_clarify"
            return renderer.render_glucose_unit_clarify(session.state.role)

        result = engine.evaluate(session.state)

        if isinstance(result, Refusal):
            return renderer.render_refusal(result, session.state.role)

        if isinstance(result, NeedsInfo):
            if result.slot == "presenting_complaint":
                session.pending_slot = "presenting_complaint"
                return renderer.render_presenting_complaint_question(session.state.role)
            session.pending_slot = result.slot
            session.last_needs_info_tier = result.highest_reachable_tier
            return renderer.render_slot_question(result.slot, session.state.role)

        return self._finalize(session, result)

    def _finalize(self, session: Session, verdict: Verdict) -> OutboundMessage:
        session.verdict = verdict
        session.terminal = True
        session.pending_slot = None
        if "SN1" in verdict.fired_rule_ids:
            return renderer.render_non_diabetes_emergency_exit()
        if "SN2" in verdict.fired_rule_ids:
            return renderer.render_pregnancy_exit()
        return renderer.render_verdict(verdict, session.state.role)
