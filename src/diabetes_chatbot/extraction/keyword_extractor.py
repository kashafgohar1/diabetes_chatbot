"""Deterministic, network-free extractor. Needs no API key — this is what
lets the offline CLI demo and CI run with zero external dependencies.

Not part of the decision engine's import boundary (engine must not import
this module; this module may freely import engine.types purely for
documentation purposes — it does not, to keep the dependency direction
one-way and obvious).
"""

from __future__ import annotations

from .. import lexicon
from ..state import TriState
from .schema import TRISTATE_SLOTS

_CONCEPTS = {
    "unconscious_or_not_responding": lexicon.UNCONSCIOUS_OR_NOT_RESPONDING,
    "non_diabetes_emergency_signs": lexicon.NON_DIABETES_EMERGENCY,
    "pregnant": lexicon.PREGNANCY,
    "diabetes_diagnosed": lexicon.DIABETES_DIAGNOSED,
    "a_mild_symptoms": lexicon.A_MILD_SYMPTOMS,
    "a_able_to_swallow_safely": lexicon.A_ABLE_TO_SWALLOW_SAFELY,
    "a_able_to_self_treat_unaided": lexicon.A_ABLE_TO_SELF_TREAT_UNAIDED,
    "a_frequent_or_past_severe_or_impaired_awareness": lexicon.A_FREQUENT_OR_PAST_SEVERE_OR_IMPAIRED_AWARENESS,
    "b_isolated_hyperglycemia_symptoms": lexicon.B_ISOLATED_HYPERGLYCEMIA_SYMPTOMS,
    "b_dka_red_flags": lexicon.B_DKA_RED_FLAGS,
    "c_new_symptoms": lexicon.C_NEW_SYMPTOMS,
    "c_red_flags": lexicon.C_RED_FLAGS,
    "d_stable_non_infected": lexicon.D_STABLE_NON_INFECTED,
    "d_infection_signs": lexicon.D_INFECTION_SIGNS,
    "d_severe_signs": lexicon.D_SEVERE_SIGNS,
}

assert set(_CONCEPTS) == set(TRISTATE_SLOTS), "keyword extractor concept map drifted from schema.TRISTATE_SLOTS"

_YES_WORDS = {"yes", "yeah", "yep", "y", "sure", "correct", "true", "ok", "okay", "right"}
_NO_WORDS = {"no", "nope", "n", "false", "not really", "nah"}
_UNKNOWN_PHRASES = ("not sure", "unsure", "don't know", "dont know", "no idea", "not certain", "unclear", "idk")


def generic_tristate(text: str) -> TriState | None:
    t = text.strip().lower().rstrip(".! ")
    if any(p in t for p in _UNKNOWN_PHRASES):
        return TriState.UNKNOWN
    if t in _YES_WORDS:
        return TriState.YES
    if t in _NO_WORDS:
        return TriState.NO
    return None


def extract(text: str, pending_slot: str | None = None) -> dict:
    """Best-effort, offline slot extraction from free text.

    Returns a dict of {slot_name: value} for whatever could be confidently
    determined. Silence on a slot means "no update" — callers must never
    treat an absent key as NO.
    """
    updates: dict = {}

    for slot, concept in _CONCEPTS.items():
        result = lexicon.detect(text, concept)
        if result is not TriState.UNKNOWN:
            updates[slot] = result

    if pending_slot and pending_slot in _CONCEPTS and pending_slot not in updates:
        generic = generic_tristate(text)
        if generic is not None:
            updates[pending_slot] = generic

    value, unit, ambiguous = lexicon.extract_glucose_reading(text)
    if value is not None:
        updates["glucose_value"] = value
        updates["glucose_unit"] = unit
        updates["glucose_unit_ambiguous"] = ambiguous

    if lexicon.detect_insulin_dose_request(text):
        updates["insulin_dose_request_detected"] = True

    return updates
