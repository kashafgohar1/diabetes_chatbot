"""Shared vocabulary between the two extractors: which slots are
extractable, and the strict JSON schema the LLM extractor is constrained to.

The engine never sees this module. It is consumed by extraction/*.py only.
"""

from __future__ import annotations

TRISTATE_SLOTS: tuple[str, ...] = (
    "unconscious_or_not_responding",
    "non_diabetes_emergency_signs",
    "pregnant",
    "diabetes_diagnosed",
    "a_mild_symptoms",
    "a_able_to_swallow_safely",
    "a_able_to_self_treat_unaided",
    "a_frequent_or_past_severe_or_impaired_awareness",
    "b_isolated_hyperglycemia_symptoms",
    "b_dka_red_flags",
    "c_new_symptoms",
    "c_red_flags",
    "d_stable_non_infected",
    "d_infection_signs",
    "d_severe_signs",
)

TRISTATE_VALUES = ("yes", "no", "unknown")

# Strict JSON schema for the LLM extractor's structured output. Every slot
# is optional (omit if not mentioned) and, if present, must be one of
# yes/no/unknown — the model is never allowed to emit a tier, a rule ID, or
# free text in place of one of these enum values.
EXTRACTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        **{slot: {"type": "string", "enum": list(TRISTATE_VALUES)} for slot in TRISTATE_SLOTS},
        "glucose_value": {"type": ["number", "null"]},
        "glucose_unit": {"type": ["string", "null"], "enum": ["mg/dL", "mmol/L", None]},
        "insulin_dose_request_detected": {"type": "boolean"},
    },
    "required": [],
    "additionalProperties": False,
}
