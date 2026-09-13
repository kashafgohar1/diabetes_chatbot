"""Deterministic red-flag pre-filter.

Runs on RAW inbound text, BEFORE any model call, on EVERY turn — including
during the consent/age-gate preamble, mid-flow, anywhere. It is what makes
"unconsciousness/seizure/not-responding escalates to Tier 3 immediately,
from any point in the conversation" true regardless of what the session
phase or extraction layer is doing.

No network, no LLM. Pure text matching via diabetes_chatbot.lexicon.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import lexicon
from .state import ClinicalState, TriState


@dataclass(frozen=True)
class RedFlagScan:
    unconscious_or_not_responding: TriState
    non_diabetes_emergency_signs: TriState
    pregnant: TriState
    insulin_dose_request_detected: bool


def scan(text: str) -> RedFlagScan:
    return RedFlagScan(
        unconscious_or_not_responding=lexicon.detect(text, lexicon.UNCONSCIOUS_OR_NOT_RESPONDING),
        non_diabetes_emergency_signs=lexicon.detect(text, lexicon.NON_DIABETES_EMERGENCY),
        pregnant=lexicon.detect(text, lexicon.PREGNANCY),
        insulin_dose_request_detected=lexicon.detect_insulin_dose_request(text),
    )


def _sticky_upgrade(current: TriState, new: TriState) -> TriState:
    """Never downgrade a red flag once raised. YES is sticky forever within
    a session; NO/UNKNOWN can still be upgraded to YES by later evidence.
    """
    if current is TriState.YES:
        return TriState.YES
    if new is TriState.YES:
        return TriState.YES
    if current is TriState.UNKNOWN:
        return new
    return current  # already NO — a later ambiguous/unknown turn doesn't erase it


def apply(state: ClinicalState, text: str) -> ClinicalState:
    """Merge this turn's red-flag scan into state, in place, and return it."""
    result = scan(text)
    state.unconscious_or_not_responding = _sticky_upgrade(
        state.unconscious_or_not_responding, result.unconscious_or_not_responding
    )
    state.non_diabetes_emergency_signs = _sticky_upgrade(
        state.non_diabetes_emergency_signs, result.non_diabetes_emergency_signs
    )
    state.pregnant = _sticky_upgrade(state.pregnant, result.pregnant)
    # Insulin-dose-request is per-turn, not sticky — it must be handled (and
    # can recur) on any turn it is asked, not just the first time.
    state.insulin_dose_request_detected = result.insulin_dose_request_detected
    return state
