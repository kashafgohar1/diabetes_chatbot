"""Clinical state: the structured representation the LLM extracts into and
the deterministic engine reads from.

Every symptom slot is tri-state (yes/no/unknown). Conflating "unknown" with
"no" turns an unasked question into a false negative — the bug class this
whole architecture exists to prevent (see OQ-9 in the protocol). A slot is
only ever NO once the corresponding question has actually been asked and
answered no; it starts, and stays, UNKNOWN otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Optional


class TriState(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

    def __bool__(self) -> bool:  # pragma: no cover - deliberately not truthy-safe
        # Force call sites to compare explicitly (state.x is TriState.YES) rather
        # than `if state.x:`, which would silently treat UNKNOWN as falsy/"no".
        raise TypeError(
            "TriState must be compared explicitly (== TriState.YES / .NO / "
            ".UNKNOWN), not used as a bool — that is exactly the unknown-as-no "
            "bug this type exists to prevent."
        )


class Role(str, Enum):
    PATIENT = "patient"
    CAREGIVER = "caregiver"


class PresentingComplaint(str, Enum):
    HYPOGLYCEMIA = "hypo"
    HYPERGLYCEMIA_DKA = "hyper_dka"
    UNDIAGNOSED = "undiagnosed"
    FOOT = "foot"
    OTHER = "other"


@dataclass
class ClinicalState:
    """Tri-state clinical variables. Populated by extraction, read (never
    written) by the decision engine. No field here may be a raw string of
    patient-authored text — that boundary belongs to the extraction layer.
    """

    # --- Session / eligibility -------------------------------------------------
    role: Optional[Role] = None
    age_over_18: TriState = TriState.UNKNOWN
    consent_given: bool = False

    # --- Global overrides (set every turn by the deterministic red-flag
    #     prefilter, from raw text, before any model call) ---------------------
    unconscious_or_not_responding: TriState = TriState.UNKNOWN  # G1
    non_diabetes_emergency_signs: TriState = TriState.UNKNOWN  # SN1
    pregnant: TriState = TriState.UNKNOWN  # SN2
    insulin_dose_request_detected: bool = False  # G2 (request, not a clinical fact)

    # --- Category gate -----------------------------------------------------
    presenting_complaint: Optional[PresentingComplaint] = None
    diabetes_diagnosed: TriState = TriState.UNKNOWN

    # --- Category A: hypoglycemia -------------------------------------------
    a_mild_symptoms: TriState = TriState.UNKNOWN
    a_able_to_swallow_safely: TriState = TriState.UNKNOWN
    a_able_to_self_treat_unaided: TriState = TriState.UNKNOWN
    a_frequent_or_past_severe_or_impaired_awareness: TriState = TriState.UNKNOWN

    # --- Category B: hyperglycemia / DKA ------------------------------------
    b_isolated_hyperglycemia_symptoms: TriState = TriState.UNKNOWN
    b_dka_red_flags: TriState = TriState.UNKNOWN

    # --- Category C: possible undiagnosed diabetes --------------------------
    c_new_symptoms: TriState = TriState.UNKNOWN
    c_red_flags: TriState = TriState.UNKNOWN

    # --- Category D: foot problems -------------------------------------------
    d_stable_non_infected: TriState = TriState.UNKNOWN
    d_infection_signs: TriState = TriState.UNKNOWN
    d_severe_signs: TriState = TriState.UNKNOWN

    # --- Glucose reading (captured for the audit trail only; OQ-8 — no rule
    #     acts on these) ------------------------------------------------------
    glucose_value: Optional[float] = None
    glucose_unit: Optional[str] = None  # "mg/dL" | "mmol/L" | None
    glucose_unit_ambiguous: bool = False

    def get(self, slot_name: str):
        return getattr(self, slot_name)

    def set(self, slot_name: str, value) -> None:
        setattr(self, slot_name, value)

    def merge_known(self, updates: dict) -> "ClinicalState":
        """Apply extractor updates, never overwriting a known value with
        UNKNOWN and never overwriting an already-YES/NO tri-state answer
        silently (the pipeline decides whether a correction is allowed).
        """
        for key, value in updates.items():
            if value is None:
                continue
            if isinstance(value, TriState) and value is TriState.UNKNOWN:
                continue
            setattr(self, key, value)
        return self


def slot_names() -> list[str]:
    return [f.name for f in fields(ClinicalState)]
